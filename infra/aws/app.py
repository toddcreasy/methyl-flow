#!/usr/bin/env python3
import os

import aws_cdk as cdk
from stacks.batch_stack import BatchStack
from stacks.site_stack import SiteStack
from stacks.traffic_stack import TrafficStack

app = cdk.App()

BatchStack(
    app,
    "MethylFlowBatchStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)

SiteStack(
    app,
    "MethylFlowSiteStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)

TrafficStack(
    app,
    "MethylFlowTrafficStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)

cdk.Tags.of(app).add("project", "methyl-flow")
cdk.Tags.of(app).add("env", "dev")
cdk.Tags.of(app).add("managed-by", "cdk")

app.synth()
