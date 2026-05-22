"""AWS CDK stack — CloudWatch dashboard, alarms, and SQS DLQ.

Provisions:
  - SQS Dead Letter Queue: marketpulse-lambda-dlq (14-day retention)
  - CloudWatch Dashboard: MarketPulse-India (6 widgets)
  - Alarm: AgentFailureRate — success < 50% over 30 min → SNS
  - Alarm: DLQMessages — any message arrives in DLQ → SNS

Synth / deploy:
    cdk synth  --app "python infra/app.py"
    cdk deploy --app "python infra/app.py" MarketPulseObservabilityStack
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import (
    aws_cloudwatch as cloudwatch,
)
from aws_cdk import (
    aws_cloudwatch_actions as cloudwatch_actions,
)
from aws_cdk import (
    aws_sns as sns,
)
from aws_cdk import (
    aws_sqs as sqs,
)
from constructs import Construct

NAMESPACE = "MarketPulseIndia"
REGION = "ap-south-1"


class ObservabilityStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Import existing SNS signals topic ────────────────────────────── #
        signals_topic = sns.Topic.from_topic_arn(
            self,
            "SignalsTopic",
            f"arn:aws:sns:{REGION}:{self.account}:marketpulse-signals",
        )

        # ── SQS Dead Letter Queue ─────────────────────────────────────────── #
        dlq = sqs.Queue(
            self,
            "MarketPulseDLQ",
            queue_name="marketpulse-lambda-dlq",
            retention_period=Duration.days(14),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── CloudWatch Dashboard ──────────────────────────────────────────── #
        dashboard = cloudwatch.Dashboard(
            self,
            "MarketPulseDashboard",
            dashboard_name="MarketPulse-India",
        )

        # Widget 1: Agent run duration
        duration_widget = cloudwatch.GraphWidget(
            title="Agent Run Duration (ms)",
            left=[
                cloudwatch.Metric(
                    namespace=NAMESPACE,
                    metric_name="AgentRunDuration",
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Avg Duration ms",
                )
            ],
            width=8,
            height=6,
        )

        # Widget 2: Agent success rate
        success_widget = cloudwatch.GraphWidget(
            title="Agent Success Rate",
            left=[
                cloudwatch.Metric(
                    namespace=NAMESPACE,
                    metric_name="AgentRunSuccess",
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Success Rate",
                )
            ],
            width=8,
            height=6,
        )

        # Widget 3: Signal distribution (BUY / HOLD / SELL per hour)
        signal_widget = cloudwatch.GraphWidget(
            title="Signals Generated",
            left=[
                cloudwatch.Metric(
                    namespace=NAMESPACE,
                    metric_name="SignalGenerated",
                    statistic="Sum",
                    period=Duration.hours(1),
                    label="BUY",
                    dimensions_map={"Direction": "BUY"},
                ),
                cloudwatch.Metric(
                    namespace=NAMESPACE,
                    metric_name="SignalGenerated",
                    statistic="Sum",
                    period=Duration.hours(1),
                    label="HOLD",
                    dimensions_map={"Direction": "HOLD"},
                ),
                cloudwatch.Metric(
                    namespace=NAMESPACE,
                    metric_name="SignalGenerated",
                    statistic="Sum",
                    period=Duration.hours(1),
                    label="SELL",
                    dimensions_map={"Direction": "SELL"},
                ),
            ],
            width=8,
            height=6,
        )

        # Widget 4: RAG retrieval precision
        retrieval_widget = cloudwatch.GraphWidget(
            title="RAG Retrieval Precision",
            left=[
                cloudwatch.Metric(
                    namespace=NAMESPACE,
                    metric_name="RetrievalPrecision",
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Precision",
                )
            ],
            width=8,
            height=6,
        )

        # Widget 5: MCP call duration
        mcp_widget = cloudwatch.GraphWidget(
            title="MCP Call Duration (ms)",
            left=[
                cloudwatch.Metric(
                    namespace=NAMESPACE,
                    metric_name="MCPCallDuration",
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Avg MCP Duration",
                )
            ],
            width=8,
            height=6,
        )

        # Widget 6: Signal confidence average
        confidence_widget = cloudwatch.GraphWidget(
            title="Signal Confidence Average",
            left=[
                cloudwatch.Metric(
                    namespace=NAMESPACE,
                    metric_name="SignalConfidence",
                    statistic="Average",
                    period=Duration.minutes(5),
                    label="Avg Confidence",
                )
            ],
            width=8,
            height=6,
        )

        dashboard.add_widgets(duration_widget, success_widget, signal_widget)
        dashboard.add_widgets(retrieval_widget, mcp_widget, confidence_widget)

        # ── Alarm: agent success rate < 50% over two 15-min periods ─────── #
        failure_alarm = cloudwatch.Alarm(
            self,
            "AgentFailureAlarm",
            metric=cloudwatch.Metric(
                namespace=NAMESPACE,
                metric_name="AgentRunSuccess",
                statistic="Average",
                period=Duration.minutes(15),
            ),
            threshold=0.5,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            evaluation_periods=2,
            alarm_description="Agent success rate below 50%",
            alarm_name="MarketPulse-AgentFailureRate",
        )
        failure_alarm.add_alarm_action(cloudwatch_actions.SnsAction(signals_topic))

        # ── Alarm: any message arrives in the DLQ ────────────────────────── #
        dlq_alarm = cloudwatch.Alarm(
            self,
            "DLQAlarm",
            metric=dlq.metric_number_of_messages_received(),
            threshold=1,
            comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
            evaluation_periods=1,
            alarm_description="Messages arriving in DLQ",
            alarm_name="MarketPulse-DLQMessages",
        )
        dlq_alarm.add_alarm_action(cloudwatch_actions.SnsAction(signals_topic))

        # ── Resource tags ─────────────────────────────────────────────────── #
        for resource in (dlq, dashboard, failure_alarm, dlq_alarm):
            Tags.of(resource).add("Project", "MarketPulse")
            Tags.of(resource).add("Env", "dev")

        # ── Stack outputs ─────────────────────────────────────────────────── #
        cdk.CfnOutput(self, "DLQUrl", value=dlq.queue_url)
        cdk.CfnOutput(self, "DashboardName", value="MarketPulse-India")


if __name__ == "__main__":
    app = cdk.App()
    ObservabilityStack(app, "MarketPulseObservabilityStack")
    app.synth()
