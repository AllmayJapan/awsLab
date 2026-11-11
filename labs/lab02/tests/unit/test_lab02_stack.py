import aws_cdk as cdk
from aws_cdk import assertions

from lab02.lab02_stack import Lab02Stack


def test_lab02_resources(monkeypatch):
    monkeypatch.setenv("ALERT_EMAIL", "ci@example.com")

    app = cdk.App(
        context={"allowedIpv4": "192.0.2.1/32"}
    )
    stack = Lab02Stack(
        app,
        "TestLab02Stack",
        env=cdk.Environment(region="ap-northeast-1"),
    )
    template = assertions.Template.from_stack(stack)

    template.resource_count_is("AWS::EC2::VPC", 1)
    template.resource_count_is(
        "AWS::ElasticLoadBalancingV2::LoadBalancer", 1
    )
    template.resource_count_is("AWS::WAFv2::WebACL", 1)

    template.has_resource_properties(
        "AWS::EC2::LaunchTemplate",
        {
            "LaunchTemplateData": {
                "MetadataOptions": {"HttpTokens": "required"}
            }
        },
    )
    template.has_resource_properties(
        "AWS::CloudWatch::Alarm",
        {
            "Namespace": "AWS/WAFV2",
            "MetricName": "BlockedRequests",
            "Threshold": 20,
        },
    )
