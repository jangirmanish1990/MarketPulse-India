"""AWS CDK stack — NSE announcement poller infrastructure.

Provisions:
  - S3 bucket for filing storage (IA after 30d, delete after 1y)
  - DynamoDB table: nse-poll-state       (per-symbol watermark)
  - DynamoDB table: nse-watched-symbols  (active symbol list)
  - Lambda function: lambdas/nse_poller/handler.py (Python 3.12, 256 MB, 60s)
  - EventBridge rule: every 5 min Mon-Fri 08:30-16:30 IST (03:00-11:00 UTC)
  - SNS topic: marketpulse-signals

Install CDK (one-time):
    pip install aws-cdk-lib constructs

Synth / deploy:
    cdk synth   --app "python infra/polling_stack.py"
    cdk deploy  --app "python infra/polling_stack.py"
"""

from __future__ import annotations

import os

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import (
    aws_dynamodb as dynamodb,
)
from aws_cdk import (
    aws_events as events,
)
from aws_cdk import (
    aws_events_targets as targets,
)
from aws_cdk import (
    aws_iam as iam,
)
from aws_cdk import (
    aws_lambda as lambda_,
)
from aws_cdk import (
    aws_s3 as s3,
)
from aws_cdk import (
    aws_sns as sns,
)
from constructs import Construct

REGION = "ap-south-1"
BUCKET_NAME = "marketpulse-india-filings"
POLL_STATE_TABLE = "nse-poll-state"
SYMBOLS_TABLE = "nse-watched-symbols"
SNS_TOPIC_NAME = "marketpulse-signals"


class NsePollerStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, env=cdk.Environment(region=REGION), **kwargs)

        # ── S3 filing bucket (pre-existing — import, do not recreate) ────── #
        filings_bucket = s3.Bucket.from_bucket_name(
            self,
            "FilingsBucket",
            BUCKET_NAME,
        )

        # ── DynamoDB: per-symbol poll watermark ───────────────────────────── #
        poll_state_table = dynamodb.Table(
            self,
            "NsePollState",
            table_name=POLL_STATE_TABLE,
            partition_key=dynamodb.Attribute(
                name="nse_symbol", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── DynamoDB: watched symbol config ───────────────────────────────── #
        watched_symbols_table = dynamodb.Table(
            self,
            "NseWatchedSymbols",
            table_name=SYMBOLS_TABLE,
            partition_key=dynamodb.Attribute(
                name="nse_symbol", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── IAM role ──────────────────────────────────────────────────────── #
        role = iam.Role(
            self,
            "NsePollerRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSLambdaBasicExecutionRole"
                )
            ],
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["s3:PutObject"],
                resources=[filings_bucket.arn_for_objects("*")],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:PutItem"],
                resources=[poll_state_table.table_arn],
            )
        )
        role.add_to_policy(
            iam.PolicyStatement(
                actions=["dynamodb:GetItem", "dynamodb:Scan"],
                resources=[watched_symbols_table.table_arn],
            )
        )

        # ── Lambda function ───────────────────────────────────────────────── #
        # FASTAPI_WEBHOOK_URL and WEBHOOK_SECRET are read from the environment
        # at synth time and injected as Lambda env vars.
        # In CI / prod, source these from AWS Secrets Manager instead.
        fastapi_webhook_url = os.environ.get("FASTAPI_WEBHOOK_URL", "http://localhost:8000/api/webhook/announcement")
        webhook_secret = os.environ.get("WEBHOOK_SECRET", "")

        poller_fn = lambda_.Function(
            self,
            "NsePollerFn",
            function_name="marketpulse-nse-poller",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset("lambdas/nse_poller"),
            role=role,
            memory_size=256,
            timeout=Duration.seconds(60),
            environment={
                "FASTAPI_WEBHOOK_URL": fastapi_webhook_url,
                "WEBHOOK_SECRET": webhook_secret,
                "NSE_POLL_STATE_TABLE": POLL_STATE_TABLE,
                "NSE_SYMBOLS_TABLE": SYMBOLS_TABLE,
                "S3_BUCKET": BUCKET_NAME,
                "LOG_LEVEL": "INFO",
            },
            description="Polls NSE announcements every 5 min and forwards to FastAPI",
        )

        # ── EventBridge rule — every 5 min Mon-Fri 08:30-16:30 IST ──────── #
        # IST = UTC+5:30 → market window 09:00-16:00 IST = 03:30-10:30 UTC
        # Using 03:00-11:00 UTC to cover pre/post-market buffer.
        # EventBridge cron: minute/5, hour 3-10, any day-of-month, any month,
        # Mon-Fri weekdays. Year field is required for EventBridge cron syntax.
        rule = events.Rule(
            self,
            "NsePollerSchedule",
            rule_name="marketpulse-nse-poller-schedule",
            description="Trigger NSE poller every 5 min on weekdays during market hours",
            schedule=events.Schedule.expression("cron(0/5 3-10 ? * MON-FRI *)"),
        )
        rule.add_target(targets.LambdaFunction(poller_fn))

        # ── SNS topic for strong-signal alerts ───────────────────────────── #
        signals_topic = sns.Topic(
            self,
            "SignalsTopic",
            topic_name=SNS_TOPIC_NAME,
            display_name="MarketPulse India — Signal Alerts",
        )

        # ── Resource tags (imported bucket excluded — CDK cannot tag it) ──── #
        for resource in (
            poll_state_table,
            watched_symbols_table,
            poller_fn,
            rule,
            signals_topic,
        ):
            Tags.of(resource).add("Project", "MarketPulse")
            Tags.of(resource).add("Env", "dev")

        # ── Stack outputs ─────────────────────────────────────────────────── #
        cdk.CfnOutput(self, "FilingsBucketName", value=filings_bucket.bucket_name)
        cdk.CfnOutput(self, "PollStateTableName", value=poll_state_table.table_name)
        cdk.CfnOutput(self, "WatchedSymbolsTableName", value=watched_symbols_table.table_name)
        cdk.CfnOutput(self, "PollerFunctionName", value=poller_fn.function_name)
        cdk.CfnOutput(self, "SignalsTopicArn", value=signals_topic.topic_arn)


# Allow running directly: python infra/polling_stack.py
if __name__ == "__main__":
    app = cdk.App()
    NsePollerStack(app, "MarketPulsePollingStack")
    app.synth()
