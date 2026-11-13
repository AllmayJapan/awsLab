import json

import aws_cdk as cdk
import pytest
from aws_cdk import assertions

from lab04.edge_stack import EdgeStack
from lab04.origin_stack import OriginStack


@pytest.fixture(scope="module")
def templates():
    app = cdk.App()
    edge = EdgeStack(app, "TestEdge", origin_bucket_name="lab04-content-111111111111-ap-northeast-1",
                     env=cdk.Environment(account="111111111111", region="us-east-1"),
                     cross_region_references=True)
    origin = OriginStack(app, "TestOrigin", bucket_name="lab04-content-111111111111-ap-northeast-1",
                         distribution_arn=edge.distribution.distribution_arn,
                         env=cdk.Environment(account="111111111111", region="ap-northeast-1"),
                         cross_region_references=True)
    app.synth()  # Catch cross-region dependency cycles and missing assets.
    return assertions.Template.from_stack(edge), assertions.Template.from_stack(origin)


def test_private_origin(templates):
    _, origin = templates
    origin.has_resource_properties("AWS::S3::Bucket", {
        "PublicAccessBlockConfiguration": {
            "BlockPublicAcls": True, "BlockPublicPolicy": True,
            "IgnorePublicAcls": True, "RestrictPublicBuckets": True},
        "OwnershipControls": {"Rules": [{"ObjectOwnership": "BucketOwnerEnforced"}]}})
    for statement in [
        {"Effect": "Allow", "Action": "s3:GetObject",
         "Principal": {"Service": "cloudfront.amazonaws.com"},
         "Condition": {"StringEquals": {"AWS:SourceArn": assertions.Match.any_value()}}},
        {"Effect": "Deny", "Condition": {"Bool": {"aws:SecureTransport": "false"}}},
    ]:
        origin.has_resource_properties("AWS::S3::BucketPolicy", {
            "PolicyDocument": {"Statement": assertions.Match.array_with([
                assertions.Match.object_like(statement)])}})
    origin.has_resource_properties("Custom::CDKBucketDeployment", {"SystemMetadata": {"cache-control": "max-age=60"}})
    origin.resource_count_is("Custom::S3AutoDeleteObjects", 1)


def test_https_oac_cache_and_waf_association(templates):
    edge, _ = templates
    edge.has_resource_properties("AWS::CloudFront::OriginAccessControl", {
        "OriginAccessControlConfig": {"OriginAccessControlOriginType": "s3",
            "SigningBehavior": "always", "SigningProtocol": "sigv4"}})
    edge.has_resource_properties("AWS::CloudFront::Distribution", {
        "DistributionConfig": {"DefaultRootObject": "index.html", "WebACLId": assertions.Match.any_value(),
            "DefaultCacheBehavior": {"ViewerProtocolPolicy": "redirect-to-https",
                "AllowedMethods": ["GET", "HEAD", "OPTIONS"]},
            "Origins": assertions.Match.array_with([assertions.Match.object_like({
                "OriginAccessControlId": assertions.Match.any_value(),
                "S3OriginConfig": {"OriginAccessIdentity": ""}})])}})
    edge.has_resource_properties("AWS::CloudFront::CachePolicy", {
        "CachePolicyConfig": {"DefaultTTL": 60, "MinTTL": 0, "MaxTTL": 300}})
    edge.resource_count_is("AWS::WAFv2::WebACLAssociation", 0)
    assert "s3.ap-northeast-1." in json.dumps(edge.to_json())


def test_waf_rules_and_logs(templates):
    edge, _ = templates
    edge.has_resource_properties("AWS::WAFv2::IPSet", {
        "Scope": "CLOUDFRONT", "Addresses": [], "IPAddressVersion": "IPV4"})
    acl = next(iter(edge.find_resources("AWS::WAFv2::WebACL").values()))["Properties"]
    assert acl["Scope"] == "CLOUDFRONT"
    assert acl["DefaultAction"] == {"Allow": {}}
    rules = {r["Name"]: r for r in acl["Rules"]}
    assert rules["BlockTestPath"]["Action"] == {"Block": {}}
    assert rules["BlockTestPath"]["Statement"]["ByteMatchStatement"]["SearchString"] == "/blocked-test"
    assert rules["BlockListedIPs"]["Action"] == {"Block": {}}
    for name in ("AWSManagedRulesCommonRuleSet", "AWSManagedRulesSQLiRuleSet"):
        assert rules[name]["OverrideAction"] == {"Count": {}}
    assert rules["RateLimit"]["Statement"]["RateBasedStatement"] == {
        "AggregateKeyType": "IP", "Limit": 100, "EvaluationWindowSec": 60}
    edge.has_resource_properties("AWS::Logs::LogGroup", {
        "LogGroupName": "aws-waf-logs-lab04", "RetentionInDays": 7})
    edge.resource_count_is("AWS::WAFv2::LoggingConfiguration", 1)


def test_optional_ip_list_and_managed_block():
    app = cdk.App(context={"blockedIpv4": "192.0.2.1/32,198.51.100.0/24", "managedRulesBlock": "true"})
    stack = EdgeStack(app, "ConfiguredEdge", origin_bucket_name="example-origin",
                     env=cdk.Environment(region="us-east-1"))
    template = assertions.Template.from_stack(stack)
    template.has_resource_properties("AWS::WAFv2::IPSet", {
        "Addresses": ["192.0.2.1/32", "198.51.100.0/24"]})
    rules = next(iter(template.find_resources("AWS::WAFv2::WebACL").values()))["Properties"]["Rules"]
    assert [r["OverrideAction"] for r in rules if "OverrideAction" in r] == [{"None": {}}] * 2


@pytest.mark.parametrize("cidr", ["::1/128", "invalid", "0.0.0.0/0", "192.0.2.1/24"])
def test_invalid_ipv4_rejected(cidr):
    app = cdk.App(context={"blockedIpv4": cidr})
    with pytest.raises(ValueError):
        EdgeStack(app, "BadEdge", origin_bucket_name="example-origin",
                  env=cdk.Environment(region="us-east-1"))
