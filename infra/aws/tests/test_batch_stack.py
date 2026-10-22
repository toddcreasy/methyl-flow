import json

import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template
from stacks.batch_stack import BatchStack


@pytest.fixture(scope="module")
def template() -> Template:
    app = cdk.App()
    stack = BatchStack(app, "TestBatchStack")
    return Template.from_stack(stack)


def test_bucket_is_private_and_encrypted(template: Template) -> None:
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "BucketEncryption": {
                "ServerSideEncryptionConfiguration": [
                    {"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}
                ]
            },
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            },
        },
    )


def test_bucket_retained_on_delete(template: Template) -> None:
    template.has_resource(
        "AWS::S3::Bucket",
        {"DeletionPolicy": "Retain", "UpdateReplacePolicy": "Retain"},
    )


def test_bucket_enforces_ssl(template: Template) -> None:
    template.has_resource_properties(
        "AWS::S3::BucketPolicy",
        {
            "PolicyDocument": {
                "Statement": Match.array_with(
                    [
                        Match.object_like(
                            {
                                "Effect": "Deny",
                                "Condition": {"Bool": {"aws:SecureTransport": "false"}},
                            }
                        )
                    ]
                )
            }
        },
    )


def test_bucket_lifecycle_rule(template: Template) -> None:
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "LifecycleConfiguration": {
                "Rules": [
                    Match.object_like(
                        {
                            "Prefix": "work/",
                            "ExpirationInDays": 30,
                            "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 7},
                            "Status": "Enabled",
                        }
                    )
                ]
            }
        },
    )


def test_no_nat_gateway(template: Template) -> None:
    template.resource_count_is("AWS::EC2::NatGateway", 0)


def test_two_public_subnets(template: Template) -> None:
    template.resource_count_is("AWS::EC2::Subnet", 2)
    for subnet in template.find_resources("AWS::EC2::Subnet").values():
        assert subnet["Properties"]["MapPublicIpOnLaunch"] is True


def test_two_compute_environments_min_zero(template: Template) -> None:
    template.resource_count_is("AWS::Batch::ComputeEnvironment", 2)
    template.has_resource_properties(
        "AWS::Batch::ComputeEnvironment",
        {"ComputeResources": Match.object_like({"MinvCpus": 0, "Type": "SPOT"})},
    )
    template.has_resource_properties(
        "AWS::Batch::ComputeEnvironment",
        {"ComputeResources": Match.object_like({"MinvCpus": 0, "Type": "EC2"})},
    )


def test_two_job_queues(template: Template) -> None:
    template.resource_count_is("AWS::Batch::JobQueue", 2)
    template.has_resource_properties("AWS::Batch::JobQueue", {"JobQueueName": "methyl-flow-spot"})
    template.has_resource_properties(
        "AWS::Batch::JobQueue", {"JobQueueName": "methyl-flow-ondemand"}
    )


def test_launch_template_installs_miniconda(template: Template) -> None:
    launch_templates = template.find_resources("AWS::EC2::LaunchTemplate")
    assert len(launch_templates) == 1
    user_data_json = json.dumps(next(iter(launch_templates.values())))
    assert "miniconda" in user_data_json
    assert "conda install" in user_data_json
    assert "awscli" in user_data_json


def test_root_volume_is_encrypted_gp3(template: Template) -> None:
    template.has_resource_properties(
        "AWS::EC2::LaunchTemplate",
        {
            "LaunchTemplateData": Match.object_like(
                {
                    "BlockDeviceMappings": [
                        Match.object_like(
                            {
                                "Ebs": Match.object_like(
                                    {
                                        "Encrypted": True,
                                        "VolumeType": "gp3",
                                        "VolumeSize": 200,
                                        "Throughput": 1000,
                                        "Iops": 6000,
                                    }
                                )
                            }
                        )
                    ]
                }
            )
        },
    )


def test_outputs_present(template: Template) -> None:
    outputs = template.to_json().get("Outputs", {})
    for name in ("BucketName", "WorkDir", "OutDir", "SpotQueue", "OnDemandQueue", "Region"):
        assert name in outputs


def test_existing_bucket_is_imported_and_granted() -> None:
    app = cdk.App(context={"bucket_name": "my-existing-bucket"})
    template = Template.from_stack(BatchStack(app, "ImportBucketStack"))
    template.resource_count_is("AWS::S3::Bucket", 0)
    policy = json.dumps(template.find_resources("AWS::IAM::Policy"))
    assert ':s3:::my-existing-bucket"' in policy
    assert ':s3:::my-existing-bucket/*"' in policy


def test_compute_environments_track_latest_launch_template_version(template: Template) -> None:
    envs = template.find_resources("AWS::Batch::ComputeEnvironment")
    assert len(envs) == 2
    for env in envs.values():
        version = env["Properties"]["ComputeResources"]["LaunchTemplate"]["Version"]
        assert version["Fn::GetAtt"][1] == "LatestVersionNumber"


def test_every_resource_tagged() -> None:
    app = cdk.App()
    stack = BatchStack(app, "TaggedStack")
    cdk.Tags.of(app).add("project", "methyl-flow")
    cdk.Tags.of(app).add("env", "dev")
    cdk.Tags.of(app).add("managed-by", "cdk")
    template = Template.from_stack(stack)
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {"Tags": Match.array_with([{"Key": "project", "Value": "methyl-flow"}])},
    )
    template.has_resource_properties(
        "AWS::Batch::ComputeEnvironment",
        {"Tags": Match.object_like({"project": "methyl-flow", "env": "dev", "managed-by": "cdk"})},
    )


def test_max_vcpus_capped(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Batch::ComputeEnvironment",
        {"ComputeResources": Match.object_like({"MaxvCpus": 256})},
    )


def test_head_job_definition(template: Template) -> None:
    defs = template.find_resources("AWS::Batch::JobDefinition")
    assert len(defs) == 1
    props = next(iter(defs.values()))["Properties"]
    assert props["JobDefinitionName"] == "methyl-flow-nextflow-head"
    container = props["ContainerProperties"]
    assert container["Image"] == "nextflow/nextflow:25.04.0"
    assert container["Secrets"][0]["Name"] == "TOWER_ACCESS_TOKEN"
    assert "JobRoleArn" in container and "ExecutionRoleArn" in container


def test_head_role_can_drive_batch(template: Template) -> None:
    policies = json.dumps(template.find_resources("AWS::IAM::Policy"))
    for action in ("batch:SubmitJob", "batch:TerminateJob", "batch:RegisterJobDefinition"):
        assert action in policies


def test_tower_secret_has_no_committed_value(template: Template) -> None:
    template.has_resource_properties(
        "AWS::SecretsManager::Secret",
        {"Name": "methyl-flow/tower-access-token", "GenerateSecretString": Match.any_value()},
    )


def test_budget_only_with_alert_email(template: Template) -> None:
    template.resource_count_is("AWS::Budgets::Budget", 0)
    app = cdk.App(context={"alert_email": "alerts@example.com"})
    with_budget = Template.from_stack(BatchStack(app, "BudgetStack"))
    with_budget.has_resource_properties(
        "AWS::Budgets::Budget",
        {
            "Budget": Match.object_like(
                {
                    "BudgetLimit": {"Amount": 50, "Unit": "USD"},
                    "CostFilters": {"TagKeyValue": ["user:project$methyl-flow"]},
                }
            )
        },
    )


def test_head_role_reads_igenomes(template: Template) -> None:
    policies = json.dumps(template.find_resources("AWS::IAM::Policy"))
    assert "arn:aws:s3:::ngi-igenomes" in policies
    assert "arn:aws:s3:::ngi-igenomes/*" in policies


def seqera_role(template: Template) -> dict:
    roles = template.find_resources(
        "AWS::IAM::Role", {"Properties": {"RoleName": "methyl-flow-seqera"}}
    )
    assert len(roles) == 1
    return next(iter(roles.values()))["Properties"]


def test_seqera_role_trusts_only_seqera_with_external_id(template: Template) -> None:
    statements = seqera_role(template)["AssumeRolePolicyDocument"]["Statement"]
    assume = next(s for s in statements if s["Action"] == "sts:AssumeRole")
    assert assume["Principal"] == {
        "AWS": "arn:aws:iam::161471496260:role/SeqeraPlatformCloudAccessRole"
    }
    assert assume["Condition"] == {"StringEquals": {"sts:ExternalId": "pending-seqera-external-id"}}

    app = cdk.App(context={"seqera_external_id": "abc123"})
    deployed = Template.from_stack(BatchStack(app, "SeqeraIdStack"))
    statements = seqera_role(deployed)["AssumeRolePolicyDocument"]["Statement"]
    assume = next(s for s in statements if s["Action"] == "sts:AssumeRole")
    assert assume["Condition"] == {"StringEquals": {"sts:ExternalId": "abc123"}}


def test_seqera_role_cannot_create_infrastructure(template: Template) -> None:
    policies = template.find_resources("AWS::IAM::Policy")
    seqera = [
        p
        for p in policies.values()
        if any("SeqeraRole" in r["Ref"] for r in p["Properties"]["Roles"])
    ]
    actions = json.dumps(seqera)
    assert "batch:SubmitJob" in actions
    assert "iam:PassRole" in actions
    for forbidden in ("batch:CreateComputeEnvironment", "batch:CreateJobQueue", "iam:CreateRole"):
        assert forbidden not in actions


def test_ami_pinned_from_context() -> None:
    app = cdk.App(context={"ami_id": "ami-0123456789abcdef0"})
    stack = BatchStack(app, "PinnedAmiStack", env=cdk.Environment(region="us-east-1"))
    Template.from_stack(stack).has_resource_properties(
        "AWS::EC2::LaunchTemplate",
        {"LaunchTemplateData": Match.object_like({"ImageId": "ami-0123456789abcdef0"})},
    )
