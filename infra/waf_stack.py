"""AWS CDK stack — WAFv2 WebACL for CloudFront (MarketPulse India).

Provisions:
  - WAFv2 WebACL (scope=CLOUDFRONT, must deploy in us-east-1)
  - AWS managed rule: AWSManagedRulesCommonRuleSet (OWASP Top 10)
  - AWS managed rule: AWSManagedRulesKnownBadInputsRuleSet (SQLi/XSS probes)
  - IP-based rate-limit rule: 2 000 requests per 5-minute window
  - Output: WebACL ARN  (pass to CloudFront Distribution.web_acl_id on Day 29)

Note: WAFv2 WebACLs for CloudFront MUST be created in us-east-1 regardless of
where the application runs.

Synth / deploy:
    cdk synth  --app "python infra/app.py"
    cdk deploy --app "python infra/app.py" MarketPulseWafStack
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    CfnOutput,
    Stack,
    Tags,
)
from aws_cdk import aws_wafv2 as wafv2
from constructs import Construct


class MarketPulseWafStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── Managed rule group helpers ────────────────────────────────────── #
        def _managed(vendor: str, name: str, priority: int) -> wafv2.CfnWebACL.RuleProperty:
            return wafv2.CfnWebACL.RuleProperty(
                name=name,
                priority=priority,
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name=vendor,
                        name=name,
                    )
                ),
                override_action=wafv2.CfnWebACL.OverrideActionProperty(none={}),
                visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                    cloud_watch_metrics_enabled=True,
                    metric_name=name,
                    sampled_requests_enabled=True,
                ),
            )

        # ── Rate-limit rule (IP-based, 2 000 req / 5 min) ────────────────── #
        rate_limit_rule = wafv2.CfnWebACL.RuleProperty(
            name="MarketPulseRateLimit",
            priority=0,
            action=wafv2.CfnWebACL.RuleActionProperty(block={}),
            statement=wafv2.CfnWebACL.StatementProperty(
                rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                    limit=2000,
                    aggregate_key_type="IP",
                )
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="MarketPulseRateLimit",
                sampled_requests_enabled=True,
            ),
        )

        # ── WebACL ────────────────────────────────────────────────────────── #
        web_acl = wafv2.CfnWebACL(
            self,
            "MarketPulseWebACL",
            name="marketpulse-india-waf",
            scope="CLOUDFRONT",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="MarketPulseWebACL",
                sampled_requests_enabled=True,
            ),
            rules=[
                rate_limit_rule,
                _managed("AWS", "AWSManagedRulesCommonRuleSet", priority=1),
                _managed("AWS", "AWSManagedRulesKnownBadInputsRuleSet", priority=2),
            ],
            description="MarketPulse India — CloudFront WAF (OWASP + rate limit)",
        )

        # ── Resource tags ─────────────────────────────────────────────────── #
        Tags.of(web_acl).add("Project", "MarketPulse")
        Tags.of(web_acl).add("Env", "production")

        # ── Stack outputs ─────────────────────────────────────────────────── #
        CfnOutput(
            self,
            "WebAclArn",
            value=web_acl.attr_arn,
            description="WAFv2 WebACL ARN — pass to CloudFront web_acl_id",
        )
        CfnOutput(
            self,
            "WebAclId",
            value=web_acl.attr_id,
            description="WAFv2 WebACL ID",
        )
