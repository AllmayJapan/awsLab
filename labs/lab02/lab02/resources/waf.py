from constructs import Construct
from aws_cdk import (
    aws_wafv2 as wafv2,
    aws_elasticloadbalancingv2 as elbv2,
)


def visibility(metric_name: str):
    return wafv2.CfnWebACL.VisibilityConfigProperty(
        cloud_watch_metrics_enabled=True,
        metric_name=metric_name,
        sampled_requests_enabled=True,
    )


def managed_rule(
    name: str,
    priority: int,
    metric_name: str,
    block_enabled: bool,
):
    return wafv2.CfnWebACL.RuleProperty(
        name=name,
        priority=priority,
        override_action=wafv2.CfnWebACL.OverrideActionProperty(
            none={} if block_enabled else None,
            count={} if not block_enabled else None,
        ),
        statement=wafv2.CfnWebACL.StatementProperty(
            managed_rule_group_statement=(
                wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                    vendor_name="AWS",
                    name=name,
                )
            )
        ),
        visibility_config=visibility(metric_name),
    )


def rate_limit_rule():
    return wafv2.CfnWebACL.RuleProperty(
        name="Lab02RateLimit",
        priority=30,
        action=wafv2.CfnWebACL.RuleActionProperty(
            block={}
        ),
        statement=wafv2.CfnWebACL.StatementProperty(
            rate_based_statement=(
                wafv2.CfnWebACL.RateBasedStatementProperty(
                    aggregate_key_type="IP",
                    limit=100,
                    evaluation_window_sec=60,
                )
            )
        ),
        visibility_config=visibility("Lab02RateLimit"),
    )


def create_waf(
    scope: Construct,
    alb: elbv2.ApplicationLoadBalancer,
) -> tuple[wafv2.CfnWebACL, wafv2.CfnIPSet]:

    blocked_ip_set = wafv2.CfnIPSet(
        scope,
        "Lab02BlockedIpSet",
        name="lab02-blocked-ipv4",
        scope="REGIONAL",
        ip_address_version="IPV4",
        addresses=[],
        description="IPv4 block list synchronized from S3",
    )

    web_acl = wafv2.CfnWebACL(
        scope,
        "Lab02WebAcl",
        name="lab02-web-acl",
        scope="REGIONAL",
        default_action=wafv2.CfnWebACL.DefaultActionProperty(
            allow={}
        ),
        visibility_config=visibility("Lab02WebAcl"),
        rules=[
            wafv2.CfnWebACL.RuleProperty(
                name="BlockListedIPs",
                priority=0,
                action=wafv2.CfnWebACL.RuleActionProperty(
                    block={}
                ),
                statement=wafv2.CfnWebACL.StatementProperty(
                    ip_set_reference_statement=(
                        wafv2.CfnWebACL.IPSetReferenceStatementProperty(
                            arn=blocked_ip_set.attr_arn
                        )
                    )
                ),
                visibility_config=visibility("BlockListedIPs"),
            ),

            wafv2.CfnWebACL.RuleProperty(
                name="AzureAsnTest",
                priority=5,
                action=wafv2.CfnWebACL.RuleActionProperty(
                    count={}
                ),
                statement=wafv2.CfnWebACL.StatementProperty(
                    asn_match_statement=(
                        wafv2.CfnWebACL.AsnMatchStatementProperty(
                            asn_list=[8075],
                        )
                    )
                ),
                visibility_config=visibility("AzureAsnTest"),
            ),

            managed_rule(
                "AWSManagedRulesCommonRuleSet",
                10,
                "CommonRuleSet",
                block_enabled=False,
            ),
            managed_rule(
                "AWSManagedRulesSQLiRuleSet",
                20,
                "SQLiRuleSet",
                block_enabled=True,
            ),
            rate_limit_rule(),
        ],
    )

    wafv2.CfnWebACLAssociation(
        scope,
        "Lab02WebAclAssociation",
        resource_arn=alb.load_balancer_arn,
        web_acl_arn=web_acl.attr_arn,
    )

    return web_acl, blocked_ip_set
