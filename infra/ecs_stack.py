"""AWS CDK stack — ECS Fargate service for the MarketPulse India backend.

Provisions:
  - VPC (2 AZs, 1 NAT gateway)
  - ECR repository: marketpulse-india
  - ECS cluster: marketpulse-india
  - Fargate task definition (0.5 vCPU / 1 GB)
  - Application Load Balanced Fargate Service (port 80 → 8000)
  - Auto-scaling on CPU utilisation (1–3 tasks, target 70%)

Synth / deploy:
    cdk synth  --app "python infra/app.py"
    cdk deploy --app "python infra/app.py" MarketPulseEcsStack
"""

from __future__ import annotations

import os

import aws_cdk as cdk
from aws_cdk import (
    CfnOutput,
    Duration,
    RemovalPolicy,
    Stack,
    Tags,
)
from aws_cdk import aws_ec2 as ec2
from aws_cdk import aws_ecr as ecr
from aws_cdk import aws_ecs as ecs
from aws_cdk import aws_ecs_patterns as ecs_patterns
from aws_cdk import aws_logs as logs
from aws_cdk import aws_secretsmanager as secretsmanager
from constructs import Construct


class MarketPulseEcsStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs: object) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── VPC ──────────────────────────────────────────────────────────── #
        vpc = ec2.Vpc(
            self,
            "MarketPulseVpc",
            max_azs=2,
            nat_gateways=1,
        )

        # ── ECR repository ────────────────────────────────────────────────── #
        repo = ecr.Repository(
            self,
            "MarketPulseRepo",
            repository_name="marketpulse-india",
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── ECS cluster ───────────────────────────────────────────────────── #
        cluster = ecs.Cluster(
            self,
            "MarketPulseCluster",
            vpc=vpc,
            cluster_name="marketpulse-india",
        )

        # ── Fargate task definition ───────────────────────────────────────── #
        task_def = ecs.FargateTaskDefinition(
            self,
            "MarketPulseTask",
            cpu=512,
            memory_limit_mib=1024,
        )

        # ── Secrets Manager injection ─────────────────────────────────────── #
        # Set AWS_SECRETS_NAME=<secret-name> in the environment where
        # `cdk deploy` runs (e.g. as a GitHub Actions secret).  When present,
        # all app credentials are injected as env vars before container start,
        # so os.getenv() returns real values at module-import time.
        _secrets_name = os.environ.get("AWS_SECRETS_NAME", "")
        _ecs_secrets: dict[str, ecs.Secret] = {}
        if _secrets_name:
            app_secret = secretsmanager.Secret.from_secret_name_v2(
                self, "AppSecret", _secrets_name
            )
            _ecs_secrets = {
                "OPENAI_API_KEY":    ecs.Secret.from_secrets_manager(app_secret, "OPENAI_API_KEY"),
                "DATABASE_URL":      ecs.Secret.from_secrets_manager(app_secret, "DATABASE_URL"),
                "JWT_SECRET_KEY":    ecs.Secret.from_secrets_manager(app_secret, "JWT_SECRET_KEY"),
                "LANGCHAIN_API_KEY": ecs.Secret.from_secrets_manager(app_secret, "LANGCHAIN_API_KEY"),
                "WEBHOOK_SECRET":    ecs.Secret.from_secrets_manager(app_secret, "WEBHOOK_SECRET"),
            }

        container = task_def.add_container(
            "MarketPulseContainer",
            image=ecs.ContainerImage.from_ecr_repository(repo),
            environment={
                "TZ": "Asia/Kolkata",
                "ENV": "production",
                "AWS_SECRETS_NAME": _secrets_name,
            },
            secrets=_ecs_secrets,
            logging=ecs.LogDrivers.aws_logs(
                stream_prefix="marketpulse",
                log_retention=logs.RetentionDays.ONE_WEEK,
            ),
            health_check=ecs.HealthCheck(
                command=["CMD-SHELL", "curl -f http://localhost:8000/health || exit 1"],
                interval=Duration.seconds(30),
                timeout=Duration.seconds(10),
                retries=3,
                start_period=Duration.seconds(40),
            ),
        )

        container.add_port_mappings(ecs.PortMapping(container_port=8000))

        # ── ALB + Fargate service ─────────────────────────────────────────── #
        service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "MarketPulseService",
            cluster=cluster,
            task_definition=task_def,
            desired_count=1,
            public_load_balancer=True,
            listener_port=80,
            assign_public_ip=False,
        )

        service.target_group.configure_health_check(
            path="/health",
            healthy_http_codes="200",
            interval=Duration.seconds(30),
        )

        # ── Auto-scaling ──────────────────────────────────────────────────── #
        scaling = service.service.auto_scale_task_count(max_capacity=3, min_capacity=1)
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=70,
            scale_in_cooldown=Duration.seconds(60),
            scale_out_cooldown=Duration.seconds(30),
        )

        # ── Resource tags ─────────────────────────────────────────────────── #
        for resource in (vpc, repo, cluster, task_def, service.service):
            Tags.of(resource).add("Project", "MarketPulse")
            Tags.of(resource).add("Env", "production")

        # ── Stack outputs ─────────────────────────────────────────────────── #
        CfnOutput(
            self,
            "LoadBalancerDNS",
            value=service.load_balancer.load_balancer_dns_name,
            description="ALB DNS — use as BACKEND_URL",
        )
        CfnOutput(self, "EcrRepositoryUri", value=repo.repository_uri)
        CfnOutput(self, "ClusterName", value=cluster.cluster_name)
