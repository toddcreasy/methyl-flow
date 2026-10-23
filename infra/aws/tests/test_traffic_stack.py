import aws_cdk as cdk
import pytest
from aws_cdk.assertions import Match, Template
from stacks.traffic_stack import TrafficStack


@pytest.fixture(scope="module")
def template() -> Template:
    app = cdk.App(context={"traffic_email": "traffic@example.com"})
    return Template.from_stack(TrafficStack(app, "TestTrafficStack"))


def test_requires_an_email() -> None:
    with pytest.raises(ValueError, match="traffic_email"):
        TrafficStack(cdk.App(), "NoEmail")


def test_daily_schedule_invokes_the_function(template: Template) -> None:
    template.has_resource_properties(
        "AWS::Scheduler::Schedule",
        {
            "ScheduleExpression": "cron(0 7 * * ? *)",
            "ScheduleExpressionTimezone": "America/New_York",
            "State": "ENABLED",
        },
    )
    template.has_resource_properties(
        "AWS::Lambda::Function",
        {
            "FunctionName": "methyl-flow-github-traffic",
            "Environment": {
                "Variables": Match.object_like({"GITHUB_REPO": "toddcreasy/methyl-flow"})
            },
        },
    )


def test_bucket_is_private(template: Template) -> None:
    template.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": {
                "BlockPublicAcls": True,
                "BlockPublicPolicy": True,
                "IgnorePublicAcls": True,
                "RestrictPublicBuckets": True,
            }
        },
    )


def test_email_and_failure_alarm(template: Template) -> None:
    template.has_resource_properties(
        "AWS::SNS::Subscription", {"Protocol": "email", "Endpoint": "traffic@example.com"}
    )
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm", {"AlarmName": "methyl-flow-github-traffic-errors"}
    )
    template.has_resource_properties(
        "AWS::SecretsManager::Secret", {"Name": "methyl-flow/github-traffic-token"}
    )
