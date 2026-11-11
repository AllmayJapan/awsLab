import os

from lab02.resources.monitoring import (
    create_waf_logging,
    create_waf_alerting,
)
from aws_cdk import Stack, CfnOutput
from constructs import Construct

from lab02.resources.network import create_network
from lab02.resources.compute import create_compute
from lab02.resources.load_balancer import create_load_balancer
from lab02.resources.waf import create_waf
from lab02.resources.monitoring import create_waf_logging
from lab02.resources.ip_list import (
    create_ip_list_bucket,
    create_ip_list_sync,
)

# Hello World
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
        web_acl, blocked_ip_set = create_waf(
            self,
            alb,
        )

        # Ip List strage
        ip_list_bucket = create_ip_list_bucket(self)

        ip_list_sync = create_ip_list_sync(
            self,
            ip_list_bucket,
            blocked_ip_set,
        )
        # Monitoring
        create_waf_logging(
            self,
            web_acl,
        )

        alert_email = os.environ.get("ALERT_EMAIL")

        if not alert_email:
            raise ValueError(
                "ALERT_EMAIL is not configured"
            )

        create_waf_alerting(
            self,
            alert_email,
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

        CfnOutput(
            self,
            "IpListBucketName",
            value=ip_list_bucket.bucket_name,
        )

        CfnOutput(
            self,
            "BlockedIpSetId",
            value=blocked_ip_set.attr_id,
        )

        CfnOutput(
            self,
            "IpListSyncFunctionName",
            value=ip_list_sync.function_name,
        )