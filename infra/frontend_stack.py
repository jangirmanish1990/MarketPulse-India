"""AWS CDK stack — CloudFront + S3 for the MarketPulse India React dashboard.

Provisions:
  - S3 bucket: marketpulse-india-frontend-{account}
      (all public access blocked; served exclusively through CloudFront OAC)
  - CloudFront distribution with Origin Access Control
      HTTPS redirect, CACHING_OPTIMIZED, PRICE_CLASS_200
      SPA routing: 403/404 → index.html (200)

Note: this stack must be deployed to us-east-1 — CloudFront is a global
service whose AWS control plane lives in us-east-1.

Synth / deploy:
    cdk synth  --app "python infra/app.py"
    cdk deploy --app "python infra/app.py" MarketPulseFrontendStack
"""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import aws_cloudfront as cloudfront
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from constructs import Construct


class MarketPulseFrontendStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 bucket — private, served only via CloudFront OAC ──────────── #
        bucket = s3.Bucket(
            self,
            "FrontendBucket",
            bucket_name=f"marketpulse-india-frontend-{self.account}",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,
            auto_delete_objects=False,
        )

        # ── CloudFront distribution ───────────────────────────────────────── #
        distribution = cloudfront.Distribution(
            self,
            "FrontendDistribution",
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                cache_policy=cloudfront.CachePolicy.CACHING_OPTIMIZED,
                compress=True,
            ),
            price_class=cloudfront.PriceClass.PRICE_CLASS_200,
            default_root_object="index.html",
            # SPA routing — React Router handles paths; 403/404 from S3 → index.html
            error_responses=[
                cloudfront.ErrorResponse(
                    http_status=404,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
                cloudfront.ErrorResponse(
                    http_status=403,
                    response_http_status=200,
                    response_page_path="/index.html",
                    ttl=Duration.seconds(0),
                ),
            ],
            comment="MarketPulse India — React Dashboard",
        )

        # ── Resource tags ─────────────────────────────────────────────────── #
        for resource in (bucket, distribution):
            Tags.of(resource).add("Project", "MarketPulse")
            Tags.of(resource).add("Env", "production")

        # ── Stack outputs ─────────────────────────────────────────────────── #
        CfnOutput(
            self,
            "CloudFrontURL",
            value=f"https://{distribution.distribution_domain_name}",
            description="React dashboard URL",
        )
        CfnOutput(
            self,
            "BucketName",
            value=bucket.bucket_name,
            description="S3 bucket for frontend assets",
        )
        CfnOutput(
            self,
            "DistributionId",
            value=distribution.distribution_id,
            description="CloudFront distribution ID for cache invalidation",
        )
