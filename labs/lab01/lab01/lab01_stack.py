from pathlib import Path

from aws_cdk import (
    CfnOutput,
    CfnParameter,
    Duration,
    RemovalPolicy,
    Stack,
    aws_apigateway as apigateway,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_wafv2 as wafv2,
    # aws_sqs as sqs,
)
from constructs import Construct

class Lab01Stack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # The code that defines your stack goes here
        allowed_ipv4 = CfnParameter(
            self,
            "AllowedIpv4",
            type="String",
            description="Your public IPv4 CIDR, for example 203.0.113.10/32",
        )

        lambda_logs = logs.LogGroup(
            self,
            "LambdaLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        api_logs = logs.LogGroup(
            self,
            "ApiAccessLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        waf_logs = logs.LogGroup(
            self,
            "WafLogs",
            log_group_name=f"aws-waf-logs-{self.stack_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        application_dir = (
            Path(__file__).resolve().parent.parent / "application"
        )

        function = lambda_.Function(
            self,
            "WebFunction",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler="handler.handler",
            code=lambda_.Code.from_asset(str(application_dir)),
            memory_size=128,
            timeout=Duration.seconds(5),
            log_group=lambda_logs,
        )

        api = apigateway.RestApi(
            self,
            "WebApi",
            endpoint_types=[apigateway.EndpointType.REGIONAL],
            cloud_watch_role=True,
            cloud_watch_role_removal_policy=RemovalPolicy.DESTROY,
            deploy_options=apigateway.StageOptions(
                stage_name="lab",
                throttling_rate_limit=5,
                throttling_burst_limit=10,
                access_log_destination=apigateway.LogGroupLogDestination(
                    api_logs
                ),
                access_log_format=(
                    apigateway.AccessLogFormat.json_with_standard_fields(
                        caller=True,
                        http_method=True,
                        ip=True,
                        protocol=True,
                        request_time=True,
                        resource_path=True,
                        response_length=True,
                        status=True,
                        user=True,
                    )
                ),
            ),
        )

        integration = apigateway.LambdaIntegration(function)

        # GET /
        api.root.add_method("GET", integration)

        # GET /search
        search = api.root.add_resource("search")
        search.add_method("GET", integration)

        # 5. IP request for experiment
        allowed_ips = wafv2.CfnIPSet(
            self,
            "AllowedIps",
            scope="REGIONAL",
            ip_address_version="IPV4",
            addresses=[allowed_ipv4.value_as_string],
        )

        # The helper function to create metrics configure
        def visibility(name: str):
            return wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                sampled_requests_enabled=False,
                metric_name=name,
            )

        # The helper function to add Managed Rule Group by Count
        def managed_rule(name: str, priority: int):
            return wafv2.CfnWebACL.RuleProperty(
                name=name,
                priority=priority,
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=(
                        wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                            vendor_name="AWS",
                            name=name,
                        )
                    ),
                ),
                override_action=wafv2.CfnWebACL.OverrideActionProperty(
                    count={}
                ),
                visibility_config=visibility(name),
            )

        web_acl = wafv2.CfnWebACL(
            self,
            "WebAcl",
            scope="REGIONAL",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(
                allow={}
            ),
            visibility_config=visibility("Lab01WebAcl"),
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    name="BlockOutsideLab",
                    priority=0,
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        not_statement=wafv2.CfnWebACL.NotStatementProperty(
                            statement=wafv2.CfnWebACL.StatementProperty(
                                ip_set_reference_statement=(
                                    wafv2.CfnWebACL.IPSetReferenceStatementProperty(
                                        arn=allowed_ips.attr_arn
                                    )
                                ),
                            )
                        ),
                    ),
                    visibility_config=visibility("BlockOutsideLab"),
                ),
                wafv2.CfnWebACL.RuleProperty(
                    name="RateLimit",
                    priority=10,
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=(
                            wafv2.CfnWebACL.RateBasedStatementProperty(
                                aggregate_key_type="IP",
                                limit=300,
                                evaluation_window_sec=300,
                            )
                        ),
                    ),
                    visibility_config=visibility("RateLimit"),
                ),
                managed_rule("AWSManagedRulesCommonRuleSet", 20),
                managed_rule("AWSManagedRulesSQLiRuleSet", 30),
            ],
        )

        wafv2.CfnWebACLAssociation(
            self,
            "WebAclAssociation",
            resource_arn=api.deployment_stage.stage_arn,
            web_acl_arn=web_acl.attr_arn,
        )

        waf_log_arn = (
            f"arn:{self.partition}:logs:{self.region}:{self.account}"
            f":log-group:{waf_logs.log_group_name}"
        )

        wafv2.CfnLoggingConfiguration(
            self,
            "WafLogging",
            resource_arn=web_acl.attr_arn,
            log_destination_configs=[waf_log_arn],
        )

        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(
            self,
            "WafLogGroupName",
            value=waf_logs.log_group_name,
        )

        # example resource
        # queue = sqs.Queue(
        #     self, "Lab01Queue",
        #     visibility_timeout=Duration.seconds(300),
        # )
