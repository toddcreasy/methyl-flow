"""AWS Batch infrastructure for running every methyl-flow pipeline on AWS.

Mirrors the `aws` profile in config/methylseq/compute.config: a job queue + S3 work dir
that Nextflow's awsbatch executor points at, and an instance AMI that carries
the AWS CLI at /home/ec2-user/miniconda/bin/aws (aws.batch.cliPath default).

The Nextflow head process also runs here, as a Batch job on the on-demand queue,
so a laptop only submits runs (scripts/run_methylseq.sh, scripts/run_fetch.sh).
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Size,
    Stack,
)
from aws_cdk import aws_batch as batch
from aws_cdk import aws_budgets as budgets
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct

# Instance families suitable for bioinformatics workloads (general, compute,
# and memory optimized). All x86_64: nf-core containers are amd64, so
# Graviton/arm64 classes are excluded.
INSTANCE_CLASSES = [
    ec2.InstanceClass.M5,
    ec2.InstanceClass.M6I,
    ec2.InstanceClass.C5,
    ec2.InstanceClass.C6I,
    ec2.InstanceClass.R5,
    ec2.InstanceClass.R6I,
]

# Nextflow version pinned in scripts/run_methylseq.sh (methylseq 4.2.0's CI version).
NEXTFLOW_IMAGE = "nextflow/nextflow:25.04.0"

# Actions the Nextflow head process needs to drive the awsbatch executor
# (https://docs.seqera.io/nextflow/aws), plus logs:GetLogEvents so failed-task
# reports can include the task's log.
HEAD_JOB_ACTIONS = [
    "batch:CancelJob",
    "batch:DescribeComputeEnvironments",
    "batch:DescribeJobDefinitions",
    "batch:DescribeJobQueues",
    "batch:DescribeJobs",
    "batch:ListJobs",
    "batch:RegisterJobDefinition",
    "batch:SubmitJob",
    "batch:TagResource",
    "batch:TerminateJob",
    "ec2:DescribeInstanceAttribute",
    "ec2:DescribeInstances",
    "ec2:DescribeInstanceStatus",
    "ec2:DescribeInstanceTypes",
    "ecs:DescribeContainerInstances",
    "ecs:DescribeTasks",
    "logs:GetLogEvents",
]

MONTHLY_BUDGET_USD = 50

# Seqera Cloud assumes customer roles from this role
# (https://docs.seqera.io/platform-cloud/compute-envs/aws-batch, IAM role-based credentials).
SEQERA_CLOUD_PRINCIPAL = "arn:aws:iam::161471496260:role/SeqeraPlatformCloudAccessRole"
# Seqera generates the external ID only after the credential is saved with this role's ARN, so
# the first deploy uses a placeholder Seqera never presents; redeploy with -c seqera_external_id.
SEQERA_EXTERNAL_ID_PLACEHOLDER = "pending-seqera-external-id"

MINICONDA_INSTALL_DIR = "/home/ec2-user/miniconda"
MINIFORGE_URL = (
    "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
)


class BatchStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        max_vcpus = int(self.node.try_get_context("max_vcpus") or 256)
        root_volume_gb = int(self.node.try_get_context("root_volume_gb") or 200)

        existing_bucket_name = self.node.try_get_context("bucket_name")

        # --- S3: work dir + results ---------------------------------------
        # With -c bucket_name=<name>, use that existing bucket instead of
        # creating one. Its lifecycle and access settings stay the owner's.
        if existing_bucket_name:
            bucket = s3.Bucket.from_bucket_name(self, "Bucket", existing_bucket_name)
        else:
            bucket = self._create_bucket()
        work_dir = f"s3://{bucket.bucket_name}/work"
        out_dir = f"s3://{bucket.bucket_name}/results"

        # --- Network: public-subnet-only VPC, no NAT ------------------------
        vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                )
            ],
            gateway_endpoints={
                "S3": ec2.GatewayVpcEndpointOptions(
                    service=ec2.GatewayVpcEndpointAwsService.S3,
                )
            },
        )

        security_group = ec2.SecurityGroup(
            self,
            "ComputeSg",
            vpc=vpc,
            description="AWS Batch compute instances: no inbound, egress only",
            allow_all_outbound=True,
        )

        # --- IAM: EC2 instance role -----------------------------------------
        instance_role = iam.Role(
            self,
            "InstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonEC2ContainerServiceforEC2Role"
                ),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore"),
            ],
        )
        bucket.grant_read_write(instance_role)

        # --- Launch template: AL2023 ECS-optimized AMI + Miniforge (conda-forge only,
        # avoids Anaconda default-channel licensing) at the miniconda path ----
        # Batch merges its own ECS bootstrap user data with this one, so it
        # must be MIME multipart.
        install_commands = ec2.UserData.for_linux()
        install_commands.add_commands(
            f"curl -fsSL {MINIFORGE_URL} -o /tmp/miniconda.sh",
            f"bash /tmp/miniconda.sh -b -p {MINICONDA_INSTALL_DIR}",
            f"{MINICONDA_INSTALL_DIR}/bin/conda install -y awscli",
            "rm -f /tmp/miniconda.sh",
            f"chown -R ec2-user:ec2-user {MINICONDA_INSTALL_DIR}",
        )
        user_data = ec2.MultipartUserData()
        user_data.add_user_data_part(
            install_commands, ec2.MultipartBody.SHELL_SCRIPT, make_default=True
        )

        # A new AMI rolls every Batch instance, stopping running jobs after 30 minutes, so
        # cdk.json pins it; drop ami_id to resolve the latest ECS-optimized AL2023 AMI.
        ami_id = self.node.try_get_context("ami_id")
        machine_image = (
            ec2.MachineImage.generic_linux({self.region: ami_id})
            if ami_id
            else ecs.EcsOptimizedImage.amazon_linux2023(ecs.AmiHardwareType.STANDARD)
        )

        launch_template = ec2.LaunchTemplate(
            self,
            "LaunchTemplate",
            machine_image=machine_image,
            block_devices=[
                ec2.BlockDevice(
                    device_name="/dev/xvda",
                    volume=ec2.BlockDeviceVolume.ebs(
                        root_volume_gb,
                        volume_type=ec2.EbsDeviceVolumeType.GP3,
                        # gp3 baseline (125 MiB/s) saturates when several tasks
                        # stage the Bismark index at once, and container starts time out
                        throughput=1000,
                        iops=6000,
                        encrypted=True,
                    ),
                )
            ],
            user_data=user_data,
        )

        # --- Batch: SPOT + ON_DEMAND compute environments -------------------
        common_env_props = dict(
            vpc=vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[security_group],
            instance_role=instance_role,
            launch_template=launch_template,
            instance_classes=INSTANCE_CLASSES,
            use_optimal_instance_classes=False,
            minv_cpus=0,
            maxv_cpus=max_vcpus,
        )

        spot_env = batch.ManagedEc2EcsComputeEnvironment(
            self,
            "SpotComputeEnvironment",
            spot=True,
            allocation_strategy=batch.AllocationStrategy.SPOT_PRICE_CAPACITY_OPTIMIZED,
            **common_env_props,
        )

        ondemand_env = batch.ManagedEc2EcsComputeEnvironment(
            self,
            "OnDemandComputeEnvironment",
            spot=False,
            allocation_strategy=batch.AllocationStrategy.BEST_FIT_PROGRESSIVE,
            **common_env_props,
        )

        # Batch pins the launch template version it saw at creation; track the
        # latest version so template changes (e.g. root volume size) reach new instances.
        for env in (spot_env, ondemand_env):
            env.node.default_child.add_property_override(
                "ComputeResources.LaunchTemplate.Version",
                launch_template.latest_version_number,
            )

        spot_queue = batch.JobQueue(
            self,
            "SpotJobQueue",
            job_queue_name="methyl-flow-spot",
            compute_environments=[
                batch.OrderedComputeEnvironment(compute_environment=spot_env, order=1)
            ],
        )

        ondemand_queue = batch.JobQueue(
            self,
            "OnDemandJobQueue",
            job_queue_name="methyl-flow-ondemand",
            compute_environments=[
                batch.OrderedComputeEnvironment(compute_environment=ondemand_env, order=1)
            ],
        )

        # --- Nextflow head job ------------------------------------------------
        # Seqera Platform token. CDK creates it with a random placeholder; the real
        # value is set out of band with `aws secretsmanager put-secret-value`, so it
        # never appears in code or the template.
        tower_secret = secretsmanager.Secret(
            self,
            "TowerAccessToken",
            secret_name="methyl-flow/tower-access-token",
            description="Seqera Platform access token for Nextflow -with-tower",
        )

        execution_role = iam.Role(
            self,
            "HeadExecutionRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AmazonECSTaskExecutionRolePolicy"
                )
            ],
        )
        tower_secret.grant_read(execution_role)

        head_role = iam.Role(
            self,
            "HeadJobRole",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
        )
        head_role.add_to_policy(iam.PolicyStatement(actions=HEAD_JOB_ACTIONS, resources=["*"]))
        bucket.grant_read_write(head_role)
        # nf-core pipelines validate that igenomes_base (s3://ngi-igenomes) exists even when
        # iGenomes is unused, and a role-signed request to a public bucket needs IAM allow.
        head_role.add_to_policy(
            iam.PolicyStatement(actions=["s3:ListBucket"], resources=["arn:aws:s3:::ngi-igenomes"])
        )
        head_role.add_to_policy(
            iam.PolicyStatement(actions=["s3:GetObject"], resources=["arn:aws:s3:::ngi-igenomes/*"])
        )

        head_job = batch.EcsJobDefinition(
            self,
            "HeadJobDefinition",
            job_definition_name="methyl-flow-nextflow-head",
            container=batch.EcsEc2ContainerDefinition(
                self,
                "HeadContainer",
                image=ecs.ContainerImage.from_registry(NEXTFLOW_IMAGE),
                cpu=2,
                memory=Size.mebibytes(6144),
                command=["nextflow", "-version"],
                job_role=head_role,
                execution_role=execution_role,
                environment={
                    "NXF_OPTS": "-Xms512m -Xmx4g",
                    "NXF_ANSI_LOG": "false",
                },
                secrets={"TOWER_ACCESS_TOKEN": batch.Secret.from_secrets_manager(tower_secret)},
            ),
        )

        # --- Seqera Platform ---------------------------------------------------
        # Role Seqera Cloud assumes for a manual compute environment on the queues above.
        # It submits and watches head jobs and reads logs and the bucket; it creates no
        # Batch or IAM resources. The head job it launches runs as head_role.
        seqera_role = iam.Role(
            self,
            "SeqeraRole",
            role_name="methyl-flow-seqera",
            assumed_by=iam.ArnPrincipal(SEQERA_CLOUD_PRINCIPAL),
            external_ids=[
                self.node.try_get_context("seqera_external_id") or SEQERA_EXTERNAL_ID_PLACEHOLDER
            ],
            description="Seqera Platform credential for the methyl-flow Batch queues",
        )
        seqera_role.assume_role_policy.add_statements(
            iam.PolicyStatement(
                actions=["sts:TagSession"],
                principals=[iam.ArnPrincipal(SEQERA_CLOUD_PRINCIPAL)],
            )
        )
        seqera_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "batch:DescribeComputeEnvironments",
                    "batch:DescribeJobDefinitions",
                    "batch:DescribeJobQueues",
                    "batch:DescribeJobs",
                ],
                resources=["*"],
            )
        )
        seqera_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "batch:CancelJob",
                    "batch:RegisterJobDefinition",
                    "batch:SubmitJob",
                    "batch:TagResource",
                    "batch:TerminateJob",
                ],
                resources=[
                    spot_queue.job_queue_arn,
                    ondemand_queue.job_queue_arn,
                    f"arn:aws:batch:{self.region}:{self.account}:job-definition/*",
                    f"arn:aws:batch:{self.region}:{self.account}:job/*",
                ],
            )
        )
        head_role.grant_pass_role(seqera_role)
        seqera_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "logs:Describe*",
                    "logs:FilterLogEvents",
                    "logs:Get*",
                    "logs:List*",
                    "logs:StartQuery",
                    "logs:StopQuery",
                ],
                resources=[f"arn:aws:logs:{self.region}:{self.account}:log-group:/aws/batch/job*"],
            )
        )
        bucket.grant_read(seqera_role)

        # --- Cost guardrail -----------------------------------------------------
        # Alerts only; nothing is stopped. Filters on the project cost allocation
        # tag, so it counts only this stack's resources. ALERT_EMAIL comes from
        # context (-c alert_email=...) so the address is not committed.
        alert_email = self.node.try_get_context("alert_email")
        if alert_email:
            subscribers = [
                budgets.CfnBudget.SubscriberProperty(subscription_type="EMAIL", address=alert_email)
            ]
            budgets.CfnBudget(
                self,
                "MonthlyBudget",
                budget=budgets.CfnBudget.BudgetDataProperty(
                    budget_name="methyl-flow-monthly",
                    budget_type="COST",
                    time_unit="MONTHLY",
                    budget_limit=budgets.CfnBudget.SpendProperty(
                        amount=MONTHLY_BUDGET_USD, unit="USD"
                    ),
                    cost_filters={"TagKeyValue": ["user:project$methyl-flow"]},
                ),
                notifications_with_subscribers=[
                    budgets.CfnBudget.NotificationWithSubscribersProperty(
                        notification=budgets.CfnBudget.NotificationProperty(
                            comparison_operator="GREATER_THAN",
                            notification_type=kind,
                            threshold=pct,
                            threshold_type="PERCENTAGE",
                        ),
                        subscribers=subscribers,
                    )
                    for kind, pct in (("ACTUAL", 80), ("ACTUAL", 100), ("FORECASTED", 100))
                ],
            )

        # --- Outputs ----------------------------------------------------------
        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "WorkDir", value=work_dir)
        CfnOutput(self, "OutDir", value=out_dir)
        CfnOutput(self, "SpotQueue", value=spot_queue.job_queue_name)
        CfnOutput(self, "OnDemandQueue", value=ondemand_queue.job_queue_name)
        CfnOutput(self, "Region", value=self.region)
        CfnOutput(self, "HeadJobDefinitionName", value=head_job.job_definition_name)
        CfnOutput(self, "TowerSecretName", value=tower_secret.secret_name)
        CfnOutput(self, "SeqeraRoleArn", value=seqera_role.role_arn)
        CfnOutput(self, "HeadJobRoleArn", value=head_role.role_arn)
        CfnOutput(
            self,
            "EnvSnippet",
            value=(
                f"AWS_REGION={self.region} "
                f"AWS_BATCH_QUEUE={spot_queue.job_queue_name} "
                f"AWS_S3_WORKDIR={work_dir} "
                f"AWS_S3_OUTDIR={out_dir}"
            ),
        )

    def _create_bucket(self) -> s3.Bucket:
        return s3.Bucket(
            self,
            "Bucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            versioned=False,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    id="ExpireWork",
                    prefix="work/",
                    expiration=Duration.days(30),
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                )
            ],
        )
