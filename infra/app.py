"""CDK app entry point — synthesises all MarketPulse India stacks.

Usage:
    cdk synth  --app "python infra/app.py"
    cdk deploy --app "python infra/app.py" --all
    cdk deploy --app "python infra/app.py" MarketPulseObservabilityStack
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import aws_cdk as cdk

from ecs_stack import MarketPulseEcsStack
from frontend_stack import MarketPulseFrontendStack
from observability_stack import ObservabilityStack
from polling_stack import NsePollerStack
from waf_stack import MarketPulseWafStack

app = cdk.App()

_ENV = cdk.Environment(account="775935274215", region="ap-south-1")

NsePollerStack(app, "MarketPulsePollingStack", env=_ENV)

ObservabilityStack(app, "MarketPulseObservabilityStack", env=_ENV)

MarketPulseEcsStack(app, "MarketPulseEcsStack", env=_ENV)

# CloudFront + WAF must both live in us-east-1.
_ENV_US = cdk.Environment(
    account=os.environ["CDK_DEFAULT_ACCOUNT"],
    region="us-east-1",
)

MarketPulseFrontendStack(app, "MarketPulseFrontendStack", env=_ENV_US)

# WAFv2 WebACL for CloudFront must also be provisioned in us-east-1.
MarketPulseWafStack(app, "MarketPulseWafStack", env=_ENV_US)

app.synth()
