from dataclasses import dataclass

from constructs import Construct
from aws_cdk import aws_ec2 as ec2


@dataclass
class NetworkResources:
    vpc: ec2.Vpc
    alb_sg: ec2.SecurityGroup
    app_sg: ec2.SecurityGroup
    endpoint_sg: ec2.SecurityGroup


def create_network(
    scope: Construct,
    allowed_ipv4: str,
) -> NetworkResources:

    vpc = ec2.Vpc(
        scope,
        "SaasWebVpc",
        vpc_name="lab02-saas-web-vpc",
        ip_addresses=ec2.IpAddresses.cidr("10.10.0.0/16"),
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
        scope,
        "AlbSecurityGroup",
        vpc=vpc,
        description="Security Group for Lab02 ALB",
        allow_all_outbound=False,
    )

    alb_sg.add_ingress_rule(
        peer=ec2.Peer.ipv4(allowed_ipv4),
        connection=ec2.Port.tcp(80),
        description="Allow HTTP from lab operator",
    )

    alb_sg.add_ingress_rule(
        peer=ec2.Peer.ipv4("20.27.8.194/32"),
        connection=ec2.Port.tcp(80),
        description="Allow HTTP from Azure test desktop",
    )

    app_sg = ec2.SecurityGroup(
        scope,
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

    endpoint_sg = ec2.SecurityGroup(
        scope,
        "SsmEndpointSecurityGroup",
        vpc=vpc,
        description="Allow HTTPS from Lab02 EC2 to SSM endpoints",
        allow_all_outbound=False,
    )

    endpoint_sg.add_ingress_rule(
        peer=app_sg,
        connection=ec2.Port.tcp(443),
        description="Allow HTTPS from Web EC2",
    )

    app_sg.add_egress_rule(
        peer=endpoint_sg,
        connection=ec2.Port.tcp(443),
        description="Allow HTTPS to SSM endpoints",
    )

    vpc.add_interface_endpoint(
        "SsmEndpoint",
        service=ec2.InterfaceVpcEndpointAwsService.SSM,
        subnets=ec2.SubnetSelection(
            subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
        ),
        security_groups=[endpoint_sg],
        private_dns_enabled=True,
    )

    vpc.add_interface_endpoint(
        "SsmMessagesEndpoint",
        service=ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
        subnets=ec2.SubnetSelection(
            subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
        ),
        security_groups=[endpoint_sg],
        private_dns_enabled=True,
    )

    return NetworkResources(
        vpc=vpc,
        alb_sg=alb_sg,
        app_sg=app_sg,
        endpoint_sg=endpoint_sg,
    )
