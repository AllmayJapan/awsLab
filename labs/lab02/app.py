#!/usr/bin/env python3
import os

import aws_cdk as cdk

from lab02.lab02_stack import Lab02Stack


app = cdk.App()
Lab02Stack(
    scope=app,
    construct_id="Lab02Stack",
    env=cdk.Environment(
            account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
            region='ap-northeast-1',
        ),
    )

app.synth()
