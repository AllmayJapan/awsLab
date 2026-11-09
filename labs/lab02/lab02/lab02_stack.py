from aws_cdk import (
    CfnOutput,
    Stack,
    aws_ec2 as ec2,
)
from constructs import Construct

class Lab02Stack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        vpc = ec2.Vpc(
            self,
            "SaasWebVpc",
            vpc_name="lab02-saas-web-vpc",
            ip_addresses=ec2.IpAddresses.cidr(
                "10.10.0.0/16"
            ),
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="PrivateApp",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
        )

        CfnOutput(
            self,
            "VpcId",
            value=vpc.vpc_id,
        )

        # The code that defines your stack goes here

        # example resource
        # queue = sqs.Queue(
        #     self, "Lab02Queue",
        #     visibility_timeout=Duration.seconds(300),
        # )
