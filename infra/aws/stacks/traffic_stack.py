"""Daily snapshot of the methyl-flow GitHub repo traffic, ported from glia-nav's OpsStack.

GitHub keeps repo views and clones for 14 days only. A Lambda on a daily schedule saves the raw
traffic API response to S3, merges the daily counts into history.json, and emails a summary. The
traffic API needs a token with Administration read on the repo, which the Actions GITHUB_TOKEN
cannot be granted. CloudFormation creates the secret with a random value, and the maintainer
replaces it with a fine-grained PAT.
"""

import pathlib

from aws_cdk import CfnOutput, Duration, RemovalPolicy, Stack, TimeZone
from aws_cdk import aws_cloudwatch as cw
from aws_cdk import aws_cloudwatch_actions as cw_actions
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_scheduler as scheduler
from aws_cdk import aws_scheduler_targets as targets
from aws_cdk import aws_secretsmanager as secretsmanager
from aws_cdk import aws_sns as sns
from aws_cdk import aws_sns_subscriptions as subs
from constructs import Construct

GITHUB_REPO = "toddcreasy/methyl-flow"
FUNCTION_NAME = "methyl-flow-github-traffic"
CODE = str(pathlib.Path(__file__).resolve().parents[1] / "lambdas" / "github_traffic")


class TrafficStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        email = self.node.try_get_context("traffic_email")
        if not email:
            raise ValueError("Set traffic_email in cdk.context.json or with -c traffic_email=...")

        topic = sns.Topic(
            self,
            "TrafficTopic",
            topic_name="methyl-flow-traffic",
            display_name="methyl-flow traffic",
        )
        topic.add_subscription(subs.EmailSubscription(email))
        bucket = s3.Bucket(
            self,
            "TrafficBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
        )
        token = secretsmanager.Secret(
            self,
            "GitHubTrafficToken",
            secret_name="methyl-flow/github-traffic-token",
            description=f"Fine-grained GitHub PAT, Administration read on {GITHUB_REPO}.",
        )
        function = lambda_.Function(
            self,
            "TrafficFunction",
            function_name=FUNCTION_NAME,
            description="Daily snapshot of the methyl-flow GitHub repo traffic.",
            runtime=lambda_.Runtime.PYTHON_3_14,
            architecture=lambda_.Architecture.ARM_64,
            handler="index.handler",
            code=lambda_.Code.from_asset(CODE),
            memory_size=128,
            timeout=Duration.minutes(1),
            retry_attempts=0,
            log_group=logs.LogGroup(
                self,
                "TrafficLogs",
                log_group_name=f"/aws/lambda/{FUNCTION_NAME}",
                retention=logs.RetentionDays.ONE_MONTH,
                removal_policy=RemovalPolicy.DESTROY,
            ),
            environment={
                "GITHUB_REPO": GITHUB_REPO,
                "BUCKET": bucket.bucket_name,
                "TOKEN_SECRET_ARN": token.secret_arn,
                "TOPIC_ARN": topic.topic_arn,
            },
        )
        # ListBucket lets the first run's read of the missing history.json return NoSuchKey
        # rather than AccessDenied.
        function.add_to_role_policy(
            iam.PolicyStatement(
                actions=["s3:GetObject", "s3:PutObject"], resources=[bucket.arn_for_objects("*")]
            )
        )
        function.add_to_role_policy(
            iam.PolicyStatement(actions=["s3:ListBucket"], resources=[bucket.bucket_arn])
        )
        token.grant_read(function)
        topic.grant_publish(function)
        # 7 a.m. Eastern all year: the schedule follows daylight saving time.
        scheduler.Schedule(
            self,
            "TrafficDaily",
            schedule_name="methyl-flow-github-traffic-daily",
            description="Snapshot the methyl-flow GitHub repo traffic once a day.",
            schedule=scheduler.ScheduleExpression.cron(
                minute="0", hour="7", time_zone=TimeZone.AMERICA_NEW_YORK
            ),
            target=targets.LambdaInvoke(function, retry_attempts=0),
        )
        # methyl-flow's budget emails directly rather than through a topic, so a failed run
        # alerts through the traffic topic.
        cw.Alarm(
            self,
            "TrafficErrorAlarm",
            alarm_name="methyl-flow-github-traffic-errors",
            alarm_description="The daily GitHub traffic snapshot failed. Check the token first.",
            metric=function.metric_errors(period=Duration.hours(1)),
            threshold=1,
            evaluation_periods=1,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.NOT_BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(topic))

        CfnOutput(self, "TrafficBucketName", value=bucket.bucket_name)
        CfnOutput(self, "TrafficTokenSecretName", value=token.secret_name)
