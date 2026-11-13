import ipaddress

from aws_cdk import (
    Annotations, CfnOutput, Duration, RemovalPolicy, Stack,
    aws_cloudfront as cloudfront,
    aws_cloudfront_origins as origins,
    aws_logs as logs,
    aws_s3 as s3,
    aws_wafv2 as wafv2,
)
from constructs import Construct


def visibility(name):
    return wafv2.CfnWebACL.VisibilityConfigProperty(
        cloud_watch_metrics_enabled=True, metric_name=name,
        sampled_requests_enabled=True,
    )


class EdgeStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *,
                 origin_bucket_name: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)
        blocked_ipv4 = self.node.try_get_context("blockedIpv4") or []
        if isinstance(blocked_ipv4, str):
            blocked_ipv4 = [ip.strip() for ip in blocked_ipv4.split(",") if ip.strip()]
        # Invalid CIDRs should fail before deployment.
        for cidr in blocked_ipv4:
            network = ipaddress.ip_network(cidr, strict=True)
            if network.version != 4 or network.prefixlen == 0:
                raise ValueError("blockedIpv4 must contain IPv4 CIDRs with prefix /1 to /32")
        self.ip_set = wafv2.CfnIPSet(
            self, "BlockedIPv4", scope="CLOUDFRONT",
            ip_address_version="IPV4", addresses=blocked_ipv4,
        )
        managed_block = self.node.try_get_context("managedRulesBlock") == "true"
        rules = [
            wafv2.CfnWebACL.RuleProperty(
                name="BlockTestPath", priority=0,
                action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                statement=wafv2.CfnWebACL.StatementProperty(
                    byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
                        search_string="/blocked-test", positional_constraint="EXACTLY",
                        field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(uri_path={}),
                        text_transformations=[wafv2.CfnWebACL.TextTransformationProperty(
                            priority=0, type="NONE")],
                    )), visibility_config=visibility("BlockTestPath"),
            ),
            wafv2.CfnWebACL.RuleProperty(
                name="BlockListedIPs", priority=10,
                action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                statement=wafv2.CfnWebACL.StatementProperty(
                    ip_set_reference_statement=wafv2.CfnWebACL.IPSetReferenceStatementProperty(
                        arn=self.ip_set.attr_arn)),
                visibility_config=visibility("BlockListedIPs"),
            ),
        ]
        for priority, name in [(20, "AWSManagedRulesCommonRuleSet"),
                               (30, "AWSManagedRulesSQLiRuleSet")]:
            rules.append(wafv2.CfnWebACL.RuleProperty(
                name=name, priority=priority,
                override_action=wafv2.CfnWebACL.OverrideActionProperty(
                    none={} if managed_block else None,
                    count=None if managed_block else {},
                ),
                statement=wafv2.CfnWebACL.StatementProperty(
                    managed_rule_group_statement=wafv2.CfnWebACL.ManagedRuleGroupStatementProperty(
                        vendor_name="AWS", name=name)),
                visibility_config=visibility(name),
            ))
        rules.append(wafv2.CfnWebACL.RuleProperty(
            name="RateLimit", priority=40,
            action=wafv2.CfnWebACL.RuleActionProperty(block={}),
            statement=wafv2.CfnWebACL.StatementProperty(
                rate_based_statement=wafv2.CfnWebACL.RateBasedStatementProperty(
                    aggregate_key_type="IP", limit=100, evaluation_window_sec=60)),
            visibility_config=visibility("RateLimit"),
        ))
        self.web_acl = wafv2.CfnWebACL(
            self, "WebAcl", scope="CLOUDFRONT",
            default_action=wafv2.CfnWebACL.DefaultActionProperty(allow={}),
            rules=rules, visibility_config=visibility("Lab04WebAcl"),
        )
        log_group = logs.LogGroup(
            self, "WafLogs", log_group_name="aws-waf-logs-lab04",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )
        wafv2.CfnLoggingConfiguration(
            self, "WafLogging", resource_arn=self.web_acl.attr_arn,
            log_destination_configs=[log_group.log_group_arn],
        )
        # The real bucket lives in Tokyo. Importing by attributes avoids a
        # reverse stack reference. OriginStack creates the explicit OAC policy.
        bucket = s3.Bucket.from_bucket_attributes(
            self, "TokyoOrigin", bucket_name=origin_bucket_name,
            region="ap-northeast-1",
        )
        cache_policy = cloudfront.CachePolicy(
            self, "LabCachePolicy", default_ttl=Duration.seconds(60),
            min_ttl=Duration.seconds(0), max_ttl=Duration.seconds(300),
            cookie_behavior=cloudfront.CacheCookieBehavior.none(),
            header_behavior=cloudfront.CacheHeaderBehavior.none(),
            query_string_behavior=cloudfront.CacheQueryStringBehavior.none(),
            enable_accept_encoding_gzip=True, enable_accept_encoding_brotli=True,
        )
        self.distribution = cloudfront.Distribution(
            self, "Distribution", default_root_object="index.html",
            web_acl_id=self.web_acl.attr_arn,
            default_behavior=cloudfront.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cloudfront.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                allowed_methods=cloudfront.AllowedMethods.ALLOW_GET_HEAD_OPTIONS,
                cache_policy=cache_policy, compress=True,
                response_headers_policy=cloudfront.ResponseHeadersPolicy.SECURITY_HEADERS,
            ),
        )
        # OriginStack installs the scoped policy on the real bucket. The CDK
        # warning about imported buckets is expected and handled there.
        Annotations.of(self.distribution).acknowledge_warning(
            "@aws-cdk/aws-cloudfront-origins:updateImportedBucketPolicyOac",
            "OriginStack explicitly grants this distribution s3:GetObject",
        )
        CfnOutput(self, "DistributionId", value=self.distribution.distribution_id)
        CfnOutput(self, "DistributionUrl", value=f"https://{self.distribution.distribution_domain_name}")
        CfnOutput(self, "WebAclArn", value=self.web_acl.attr_arn)
        CfnOutput(self, "WafLogGroup", value=log_group.log_group_name)
