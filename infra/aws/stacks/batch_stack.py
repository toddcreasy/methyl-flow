"""AWS Batch infrastructure for running pinned nf-core/methylseq from this repo.

Mirrors the `aws` profile in config/methylseq/compute.config: a job queue + S3 work dir
that Nextflow's awsbatch executor points at, and an instance AMI that carries
the AWS CLI at /home/ec2-user/miniconda/bin/aws (aws.batch.cliPath default).
"""

from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
)
from aws_cdk import aws_batch as batch
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_iam as iam
from aws_cdk import aws_s3 as s3
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

MINICONDA_INSTALL_DIR = "/home/ec2-user/miniconda"
MINIFORGE_URL = (
    "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh"
)


class BatchStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        max_vcpus = int(self.node.try_get_context("max_vcpus") or 64)
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

        launch_template = ec2.LaunchTemplate(
            self,
            "LaunchTemplate",
            machine_image=ecs.EcsOptimizedImage.amazon_linux2023(ecs.AmiHardwareType.STANDARD),
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

        # --- Outputs ----------------------------------------------------------
        CfnOutput(self, "BucketName", value=bucket.bucket_name)
        CfnOutput(self, "WorkDir", value=work_dir)
        CfnOutput(self, "OutDir", value=out_dir)
        CfnOutput(self, "SpotQueue", value=spot_queue.job_queue_name)
        CfnOutput(self, "OnDemandQueue", value=ondemand_queue.job_queue_name)
        CfnOutput(self, "Region", value=self.region)
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
