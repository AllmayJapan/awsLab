from constructs import Construct
from aws_cdk import (
    RemovalPolicy,
    aws_logs as logs,
    aws_wafv2 as wafv2,
)


def create_waf_logging(
    scope: Construct,
    web_acl: wafv2.CfnWebACL,
) -> logs.LogGroup:

    waf_log_group = logs.LogGroup(
        scope,
        "Lab02WafLogGroup",
        log_group_name="aws-waf-logs-lab02",
        retention=logs.RetentionDays.ONE_WEEK,
        removal_policy=RemovalPolicy.DESTROY,
    )

    waf_logging = wafv2.CfnLoggingConfiguration(
        scope,
        "Lab02WafLogging",
        resource_arn=web_acl.attr_arn,
        log_destination_configs=[
            waf_log_group.log_group_arn
        ],
    )

    waf_logging.node.add_dependency(waf_log_group)

    return waf_log_group
