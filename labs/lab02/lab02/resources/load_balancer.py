from constructs import Construct
from aws_cdk import (
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
)


def create_load_balancer(
    scope: Construct,
    vpc: ec2.Vpc,
    alb_sg: ec2.SecurityGroup,
    web_instance: ec2.Instance,
) -> elbv2.ApplicationLoadBalancer:

    alb = elbv2.ApplicationLoadBalancer(
        scope,
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

    listener.add_targets(
        "WebTargetGroup",
        port=8080,
        protocol=elbv2.ApplicationProtocol.HTTP,
        targets=[
            targets.InstanceTarget(
                web_instance,
                port=8080,
            ),
        ],
        health_check=elbv2.HealthCheck(
            path="/health",
            healthy_http_codes="200",
            healthy_threshold_count=2,
            unhealthy_threshold_count=2,
        ),
    )

    return alb
