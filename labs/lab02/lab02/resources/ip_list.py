from pathlib import Path
from aws_cdk import (
    Duration,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3_notifications as s3n,
    aws_wafv2 as wafv2,
)
from aws_cdk import RemovalPolicy, aws_s3 as s3
from constructs import Construct

def create_ip_list_sync(
        scope: Construct,
        bucket: s3.Bucket,
        ip_set: wafv2.CfnIPSet,
) -> lambda_.Function:
    application_dir = (
        Path(__file__).resolve().parents[2] / "application"
    )
    object_key = "blocked-ips.json"

    log_group = logs.LogGroup(
        scope,
        "Lab02IpListSyncLogs",
        retention=logs.RetentionDays.ONE_WEEK,
        removal_policy=RemovalPolicy.DESTROY,
    )

    sync_function = lambda_.Function(
        scope,
        "Lab02IpListSync",
        runtime=lambda_.Runtime.PYTHON_3_12,
        handler="sync_ip_set.handler",
        code=lambda_.Code.from_asset(str(application_dir)),
        timeout=Duration.seconds(30),
        memory_size=128,
        reserved_concurrent_executions=1,
        log_group=log_group,
        environment={
            "IP_LIST_BUCKET": bucket.bucket_name,
            "IP_LIST_KEY": object_key,
            "IP_SET_NAME": ip_set.name,
            "IP_SET_ID": ip_set.attr_id,
        },
    )

    bucket.grant_read(sync_function, object_key)

    sync_function.add_to_role_policy(
        iam.PolicyStatement(
            actions=[
                "wafv2:GetIPSet",
                "wafv2:UpdateIPSet",
            ],
            resources=[ip_set.attr_arn],
        )
    )

    bucket.add_event_notification(
        s3.EventType.OBJECT_CREATED,
        s3n.LambdaDestination(sync_function),
        s3.NotificationKeyFilter(suffix=".json"),
    )

    return sync_function

def create_ip_list_bucket(scope: Construct) -> s3.Bucket:
    return s3.Bucket(
        scope,
        "Lab02IpListBucket",
        block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
        encryption=s3.BucketEncryption.S3_MANAGED,
        enforce_ssl=True,
        versioned=True,
        removal_policy=RemovalPolicy.RETAIN,
    )