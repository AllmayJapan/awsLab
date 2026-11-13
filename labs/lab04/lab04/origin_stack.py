from pathlib import Path

from aws_cdk import (
    CfnOutput, Duration, RemovalPolicy, Stack,
    aws_iam as iam,
    aws_s3 as s3,
    aws_s3_deployment as deployment,
)
from constructs import Construct


class OriginStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *,
                 bucket_name: str, distribution_arn: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        self.bucket = s3.Bucket(
            self, "Content", bucket_name=bucket_name,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            object_ownership=s3.ObjectOwnership.BUCKET_OWNER_ENFORCED,
            encryption=s3.BucketEncryption.S3_MANAGED,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        self.bucket.add_to_resource_policy(iam.PolicyStatement(
            principals=[iam.ServicePrincipal("cloudfront.amazonaws.com")],
            actions=["s3:GetObject"], resources=[self.bucket.arn_for_objects("*")],
            conditions={"StringEquals": {"AWS:SourceArn": distribution_arn}},
        ))
        deployment.BucketDeployment(
            self, "PublishContent", destination_bucket=self.bucket,
            sources=[deployment.Source.asset(
                str(Path(__file__).resolve().parents[1] / "application"))],
            cache_control=[deployment.CacheControl.max_age(Duration.seconds(60))],
            # CDK references the distribution only through the bucket policy.
            # Cache invalidation is a separate lab exercise.
        )
        CfnOutput(self, "BucketName", value=self.bucket.bucket_name)
