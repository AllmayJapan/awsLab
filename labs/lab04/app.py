#!/usr/bin/env python3
import os

import aws_cdk as cdk

from lab04.edge_stack import EdgeStack
from lab04.origin_stack import OriginStack

app = cdk.App()
account = os.environ.get("CDK_DEFAULT_ACCOUNT")
# Both stacks derive the same name without a reference from Edge to Origin.
# This keeps the bucket policy's reference to the distribution one-way.
bucket_name = f"lab04-content-{account or cdk.Aws.ACCOUNT_ID}-ap-northeast-1"
edge = EdgeStack(
    app, "Lab04EdgeStack", origin_bucket_name=bucket_name,
    env=cdk.Environment(account=account, region="us-east-1"),
    cross_region_references=True,
)
OriginStack(
    app, "Lab04OriginStack", bucket_name=bucket_name,
    distribution_arn=edge.distribution.distribution_arn,
    env=cdk.Environment(account=account, region="ap-northeast-1"),
    cross_region_references=True,
)
app.synth()
