#!/usr/bin/env python3
import os

import aws_cdk as cdk

from lab01.lab01_stack import Lab01Stack


app = cdk.App()
Lab01Stack(
    app,
    "Lab01Stack",
    env=cdk.Environment(
        # CDK CLIが --profile で選択した接続先アカウントを渡します。
        account=os.environ.get("CDK_DEFAULT_ACCOUNT"),
        region="ap-northeast-1",
    ),
)

app.synth()
