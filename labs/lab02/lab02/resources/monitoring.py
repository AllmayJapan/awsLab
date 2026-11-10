from constructs import Construct
from aws_cdk import (
    Duration,
    aws_cloudwatch as cloudwatch,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_sns_subscriptions as subscriptions,
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

def create_waf_alerting(
    scope: Construct,
    alert_email: str,
) -> cloudwatch.Alarm:

    # 1. SNS Topic
    topic = sns.Topic(
        scope,
        "Lab02WafAlertTopic",
        topic_name="lab02-waf-alerts",
        display_name="Lab02 WAF Alerts",
    )

    # 2. Email Subscription
    topic.add_subscription(
        subscriptions.EmailSubscription(alert_email)
    )

    # 3. WAF BlockedRequests metric
    blocked_requests = cloudwatch.Metric(
        namespace="AWS/WAFV2",
        metric_name="BlockedRequests",
        dimensions_map={
            "WebACL": "lab02-web-acl",
            "Rule": "ALL",
            "Region": scope.region,
        },
        statistic="Sum",
        period=Duration.minutes(5),
    )

    # 4. CloudWatch Alarm
    alarm = cloudwatch.Alarm(
        scope,
        "Lab02WafBlockedRequestsAlarm",
        alarm_name="lab02-waf-high-block-rate",
        alarm_description=(
            "Lab02 WAF blocked 20 or more "
            "requests in 5 minutes"
        ),
        metric=blocked_requests,
        threshold=20,
        evaluation_periods=1,
        comparison_operator=(
            cloudwatch.ComparisonOperator
            .GREATER_THAN_OR_EQUAL_TO_THRESHOLD
        ),
        treat_missing_data=(
            cloudwatch.TreatMissingData.NOT_BREACHING
        ),
    )

    # 5. Alarm -> SNS
    alarm.add_alarm_action(
        cw_actions.SnsAction(topic)
    )

    return alarm
