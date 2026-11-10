from aws_cdk import Stack, CfnOutput
from constructs import Construct

from lab02.resources.network import create_network
from lab02.resources.compute import create_compute
from lab02.resources.load_balancer import create_load_balancer
from lab02.resources.waf import create_waf
from lab02.resources.monitoring import create_waf_logging


class Lab02Stack(Stack):

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        allowed_ipv4 = self.node.try_get_context(
            "allowedIpv4"
        )

        if not allowed_ipv4:
            raise ValueError(
                "Specify -c allowedIpv4=YOUR_PUBLIC_IP/32"
            )

        # Network
        network = create_network(
            self,
            allowed_ipv4,
        )

        # Compute
        web_instance = create_compute(
            self,
            network.vpc,
            network.app_sg,
        )

        # Load Balancer
        alb = create_load_balancer(
            self,
            network.vpc,
            network.alb_sg,
            web_instance,
        )

        # WAF
        web_acl = create_waf(
            self,
            alb,
        )

        # Monitoring
        create_waf_logging(
            self,
            web_acl,
        )

        # Outputs
        CfnOutput(
            self,
            "WebInstanceId",
            value=web_instance.instance_id,
        )

        CfnOutput(
            self,
            "WebInstancePrivateIp",
            value=web_instance.instance_private_ip,
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
            value=network.vpc.vpc_id,
        )
