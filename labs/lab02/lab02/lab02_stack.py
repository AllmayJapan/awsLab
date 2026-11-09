import textwrap
from aws_cdk import (
    CfnOutput,
    Stack,
    aws_ec2 as ec2,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
    aws_iam as iam,
    aws_wafv2 as wafv2,
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

        user_data = ec2.UserData.for_linux()

        server_script = textwrap.dedent("""\
            from http.server import BaseHTTPRequestHandler, HTTPServer
            import json
            import socket

            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path == "/health":
                        body = {"status": "ok"}
                    else:
                        body = {
                            "message": "Hello from Lab02 EC2",
                            "hostname": socket.gethostname(),
                            "path": self.path,
                        }

                    data = json.dumps(body).encode("utf-8")

                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)

            HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
        """)
        service_unit = textwrap.dedent("""\
            [Unit]
            Description=Lab02 Web Application
            After=network.target

            [Service]
            ExecStart=/usr/bin/python3 /opt/lab02/server.py
            Restart=always
            RestartSec=3

            [Install]
            WantedBy=multi-user.target

        """)
        user_data.add_commands(
            "mkdir -p /opt/lab02",
            "cat > /opt/lab02/server.py <<'PY'\n"
            + server_script + "PY",
            "cat > /etc/systemd/system/lab02-web.service << 'EOF'\n"
            + service_unit + "EOF",
            "systemctl daemon-reload",
            "systemctl enable --now lab02-web",
        )

        # EC2がSystems Managerを利用するためのIAM Role
        ssm_role = iam.Role(
            self,
            "WebInstanceRole",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            description="IAM Role for Lab02 EC2 SSM access",
        )

        ssm_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name(
                "AmazonSSMManagedInstanceCore"
            )
        )

        # Interface VPC Endpoint用Security Group
        endpoint_sg = ec2.SecurityGroup(
            self,
            "SsmEndpointSecurityGroup",
            vpc=vpc,
            description="Allow HTTPS from Lab02 EC2 to SSM endpoints",
            allow_all_outbound=False,
        )

        # EC2からVPC EndpointへのHTTPS通信を許可
        endpoint_sg.add_ingress_rule(
            peer=app_sg,
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS from Web EC2",
        )

        # EC2側からVPC Endpointへの送信を許可
        app_sg.add_egress_rule(
            peer=endpoint_sg,
            connection=ec2.Port.tcp(443),
            description="Allow HTTPS to SSM endpoints",
        )

        # Systems Manager API
        vpc.add_interface_endpoint(
            "SsmEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM,
            subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[endpoint_sg],
            private_dns_enabled=True,
        )

        # Session Managerの通信チャネル
        vpc.add_interface_endpoint(
            "SsmMessagesEndpoint",
            service=ec2.InterfaceVpcEndpointAwsService.SSM_MESSAGES,
            subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            security_groups=[endpoint_sg],
            private_dns_enabled=True,
        )

        web_instance = ec2.Instance(
            self,
            "WebInstance",
            vpc=vpc,
            instance_type=ec2.InstanceType("t3.micro"),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            role=ssm_role,
            security_group=app_sg,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
            ),
            user_data=user_data,
            require_imdsv2=True,
        )

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

        # AWS WAF Web ACL
        web_acl = wafv2.CfnWebACL(
            self,
            "Lab02WebAcl",
            name="lab02-web-acl",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(
                allow={}
            ),
            visibility_config=wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                metric_name="Lab02WebAcl",
                sampled_requests_enabled=True,
            ),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesCommonRuleSet",
                    priority=0,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(
                        count={}
                    ),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=(
                            wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                                vendor_name="AWS",
                                name="AWSManagedRulesCommonRuleSet",
                            )
                        )
                    ),
                    visibility_config=(
                        wafv2.CfnWebACL.VisibilityConfigProperty(
                            cloud_watch_metrics_enabled=True,
                            metric_name="CommonRuleSet",
                            sampled_requests_enabled=True,
                        )
                    ),
                ),
                wafv2.CfnWebACL.RuleProperty(
                    name="AWSManagedRulesSQLiRuleSet",
                    priority=1,
                    override_action=wafv2.CfnWebACL.OverrideActionProperty(
                        count={}
                    ),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        managed_rule_group_statement=(
                            wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                                vendor_name="AWS",
                                name="AWSManagedRulesSQLiRuleSet",
                            )
                        )
                    ),
                    visibility_config=(
                        wafv2.CfnWebACL.VisibilityConfigProperty(
                            cloud_watch_metrics_enabled=True,
                            metric_name="SQLiRuleSet",
                            sampled_requests_enabled=True,
                        )
                    ),
                ),
            ],
        )

        # Web ACLをALBに関連付け
        wafv2.CfnWebACLAssociation(
            self,
            "Lab02WebAclAssociation",
            resource_arn=alb.load_balancer_arn,
            web_acl_arn=web_acl.attr_arn,
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
