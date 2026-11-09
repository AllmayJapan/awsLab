from aws_cdk import (
    CfnOutput,
    Stack,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
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

        alb_sg = ec2.SecurityGroup(
            self,
            "AlbSecurityGroup",
            vpc=vpc,
            description="Security Group for Lab02 ALB",
            allow_all_outbound=False,
        )

        allowed_ipv4 = self.node.try_get_context("allowedIpv4")

        if not allowed_ipv4:
            raise ValueError(
                "Specify -c allwedIpv4=YOUR_PUBLIC_IP/32"
            )

        alb_sg.add_ingress_rule(
            peer=ec2.Peer.ipv4(allowed_ipv4),
            connection=ec2.Port.tcp(80),
            description="Allow HTTP from lab operator",
        )

        app_sg = ec2.SecurityGroup(
            self,
            "AppSecurityGroup",
            vpc=vpc,
            description="Security Group for Lab02 Web App",
            allow_all_outbound=False,
        )

        app_sg.add_ingress_rule(
            peer=alb_sg,
            connection=ec2.Port.tcp(8080),
            description="Allow HTTP from ALB",
        )

        alb_sg.add_egress_rule(
            peer=app_sg,
            connection=ec2.Port.tcp(8080),
            description="Allow traffic to App",

        )

        alb = elbv2.ApplicationLoadBalancer(
            self,
            "WebAlb",
            vpc=vpc,
            internet_facing=True,
            security_group=alb_sg,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PUBLIC,
            ),
        )

        listener = alb.add_listener(
            "HttpListener",
            port=80,
            open=False,
        )

        listener.add_action(
            "DefaultResponse",
            action=elbv2.ListenerAction.fixed_response(
                status_code=200,
                content_type="text/plain",
                message_body="Lob02 ALB is running",
            ),
        )

        CfnOutput(
            self,
            "AlbDnsName",
            value=alb.load_balancer_dns_name,
        )

        CfnOutput(
            self,
            "AlbUrl",
            value=f"http://{alb.load_balancer_dns_name}",
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
