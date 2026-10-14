#!/usr/bin/env python3
import os

import aws_cdk as cdk
from stacks.batch_stack import BatchStack

app = cdk.App()

BatchStack(
    app,
    "MethylFlowBatchStack",
    env=cdk.Environment(
        account=os.getenv("CDK_DEFAULT_ACCOUNT"),
        region=os.getenv("CDK_DEFAULT_REGION"),
    ),
)

cdk.Tags.of(app).add("project", "methyl-flow")
cdk.Tags.of(app).add("env", "dev")
cdk.Tags.of(app).add("managed-by", "cdk")

app.synth()
