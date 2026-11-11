# このファイルは「AWSに何を作り、どうつなぐか」を記述する設計図です。
# Ubuntuで cdk synth / diff / deploy を実行したときに読み込まれます。
# ここに書くPythonと、AWS上でリクエストを処理するhandler.pyは役割が違います。
#
# 【構築の流れ】
# app.py → Lab01Stackの生成 → CloudFormationテンプレートへ合成
# → cdk deploy → CloudFormationがAWS上のリソースを作成・更新します。
# deployでは先にLambdaのコードをまとめ、CDKToolkitのS3へアップロードします。
#
# 【デプロイ後のリクエスト処理】
# ブラウザ/curl → API Gateway（関連付けたWAFで検査）
# → 許可されたリクエストだけLambdaへ → handler.pyのhandler()を実行
# → 戻り値をAPI GatewayがHTTPレスポンスとして返します。
# リクエストのたびにこのStackのPythonコードが実行されるわけではありません。
#
# 【参照の読み方】
# functionやapiは、AWSリソースの「定義」を表すPythonオブジェクトです。
# ARNはAWSリソースを識別する名前です。IPアドレスや接続先URLとは異なります。
# attr_arnなど、AWSに作成されてから決まる値は合成時には参照として記録され、
# CloudFormationが作成・更新するときに実際の値へ解決します。
#
# ローカルのソースコードの場所を組み立てるために使います。
from pathlib import Path

# AWSリソースの設計に使うCDKの部品を読み込みます。
# Cfnで始まる部品はCloudFormationの設定に近い形で記述するものです。
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
    # aws_sqs as sqs,  # 生成時の未使用例。コメントなので読み込まれません。
)
from constructs import Construct

# Stackは、一緒に作成・更新・削除するリソースのまとまりです。
# app.pyの Lab01Stack(app, "Lab01Stack", env=...) から呼び出されます。
class Lab01Stack(Stack):

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        # scopeは親のCDK App、construct_idはこのStackを識別する名前です。
        # **kwargsにはapp.pyから渡したアカウント・リージョンなどが入ります。
        super().__init__(scope, construct_id, **kwargs)

        # 各リソースの最初の引数selfは「このStackに所属する」の意味です。
        # 次の文字列（例："WebFunction"）はCDK内の識別子です。
        # AWS上の実名とは限らず、変更するとリソース置換につながる場合があります。

        # ── 1. デプロイ時に受け取る設定値 ──
        # AllowedIpv4は「許可する送信元IP」の入力欄です。宛先のAPIのIPではありません。
        # 例：--parameters "Lab01Stack:AllowedIpv4=自分のグローバルIPv4/32"
        # /32はIPv4を1アドレスだけ指定する書き方です。
        # ここでは値を取得せず、下のIP Setに渡す参照を用意しています。
        allowed_ipv4 = CfnParameter(
            self,
            "AllowedIpv4",
            type="String",
            description="Your public IPv4 CIDR, for example 203.0.113.10/32",
        )

        # ── 2. CloudWatch Logsの保存先を3種類用意 ──
        # ロググループはログイベントをまとめる保存先です。
        # 作成するだけでは各サービスのログは届きません。後で出力先として関連付けます。
        # ONE_WEEK：各ログイベントを7日間保存します。
        # DESTROY：cdk destroyでStackを削除すると、この保存先とログも削除します。

        # Lambdaの実行記録。handler.pyのprint()や例外を調べる場所です。
        # 下のFunctionのlog_groupで、この保存先を指定します。
        lambda_logs = logs.LogGroup(
            self,
            "LambdaLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # API Gatewayのアクセス記録。HTTPメソッド・応答コードなどを確認します。
        # 下のStageOptionsのaccess_log_destinationで指定します。
        api_logs = logs.LogGroup(
            self,
            "ApiAccessLogs",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # WAFが検査したリクエストと一致ルールを調べる保存先です。
        # WAF用のロググループ名はaws-waf-logs-から始める必要があります。
        # self.stack_nameは今回Lab01Stackなので、名前はaws-waf-logs-Lab01Stackです。
        # 下のCfnLoggingConfigurationで実際のログ出力を有効にします。
        waf_logs = logs.LogGroup(
            self,
            "WafLogs",
            log_group_name=f"aws-waf-logs-{self.stack_name}",
            retention=logs.RetentionDays.ONE_WEEK,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # ── 3. AWSで実行するLambdaと、そのコードを定義 ──
        # __file__はこのlab01_stack.pyのパスです。
        # parent.parentでプロジェクトルートへ戻り、application/を指定します。
        # 実行したターミナルの場所に依存せず、コードの場所を特定します。
        application_dir = (
            Path(__file__).resolve().parent.parent / "application"
        )

        # このFunctionはLambdaの設計です。ここでhandler()を実行するわけではありません。
        function = lambda_.Function(
            self,
            "WebFunction",
            # AWS上ではPython 3.12の実行環境を使います。
            runtime=lambda_.Runtime.PYTHON_3_12,
            # 「handler.pyのhandler関数」を呼び出しの入口として登録します。
            handler="handler.handler",
            # application/をデプロイ用にまとめます。handler.pyとindex.htmlが対象です。
            # deploy時にアップロードされ、AWS上のLambdaのコードになります。
            code=lambda_.Code.from_asset(str(application_dir)),
            # 実行に割り当てるメモリ量（MB）です。
            memory_size=128,
            # 1回の処理が5秒を超えるとLambdaの実行を打ち切ります。
            timeout=Duration.seconds(5),
            # 上で作ったLambda用ロググループへ実行ログを送ります。
            log_group=lambda_logs,
        )

        # ── 4. インターネットからHTTPリクエストを受ける入口を定義 ──
        # このREST APIがexecute-api...というHTTPS URLを提供します。
        # API GatewayがHTTPを受け付けるため、自分でEC2やWebサーバーを起動しません。
        # Function URLは作らず、このAPI経由でLambdaを呼び出す構成です。
        api = apigateway.RestApi(
            self,
            "WebApi",
            # リージョン単位の公開API。今回のリージョンはapp.pyで東京を指定しています。
            endpoint_types=[apigateway.EndpointType.REGIONAL],
            # API GatewayがCloudWatch Logsへ書き込むためのIAMロールをCDKで用意します。
            # Lambda自身の実行ロールや、手元のdefaultプロファイルとは別の役割です。
            cloud_watch_role=True,
            # Stack削除時にこのログ書き込み用ロールも削除する指定です。
            # API Gatewayのログ用ロール設定はアカウント・リージョンで共有されるため、
            # 将来別のAPIでも共有する場合は、所有するStackと削除方針を整理します。
            cloud_watch_role_removal_policy=RemovalPolicy.DESTROY,
            # ステージはAPIを公開する単位です。その公開先のログや流量を設定します。
            deploy_options=apigateway.StageOptions(
                # URLの /lab/ に相当します。Lambdaのevent.pathでは /search などになります。
                stage_name="lab",
                # 通常の処理レートの目安を毎秒5件にし、短時間のバースト枠を10にします。
                # この設定は送信元IPごとのWAFレート制限とは別です。
                # いずれも厳密な件数・費用の上限を保証するものではありません。
                throttling_rate_limit=5,
                throttling_burst_limit=10,
                # APIアクセスログを、先ほど作ったapi_logsへ送ります。
                access_log_destination=apigateway.LogGroupLogDestination(
                    api_logs
                ),
                # アクセスログに含める項目をJSON形式で指定します。
                # Trueは記録するという意味。今回は9項目すべてを明示します。
                # caller/userは呼び出し元の認証情報に関する項目で、
                # 今回のように認証を設けていない呼び出しでは値がないこともあります。
                # ここはAPIのアクセス記録で、WAFの一致ルールを記録する設定ではありません。
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

        # ── 5. URL・HTTPメソッドとLambdaの対応関係を登録 ──
        # 「このAPIからどのLambdaを呼ぶか」を指定します。
        # 既定のLambdaプロキシ統合では、パス・クエリなどをeventへまとめて渡し、
        # LambdaのstatusCode/headers/bodyをHTTPレスポンスへ反映します。
        # CDKはAPI GatewayからLambdaを呼び出すための許可も用意します。
        integration = apigateway.LambdaIntegration(function)

        # GET /lab/ → 同じLambdaのhandler() → HTMLフォームを返します。
        api.root.add_method("GET", integration)

        # GET /lab/search?q=... → 同じLambdaのhandler() → JSONを返します。
        # 実行時にはhandler.pyがevent.pathを見て、どちらの処理かを選びます。
        search = api.root.add_resource("search")
        search.add_method("GET", integration)

        # ── 6. WAFの送信元判定に使うIP Setを定義 ──
        # IP Setはアドレス一覧で、これだけでは許可・遮断をしません。
        # 下のBlockOutsideLabルールから参照して使います。
        allowed_ips = wafv2.CfnIPSet(
            self,
            "AllowedIps",
            scope="REGIONAL",
            ip_address_version="IPV4",
            # 手順1のパラメータを文字列として参照します。
            # デプロイ時に指定した「自分のグローバルIPv4/32」がここに入ります。
            addresses=[allowed_ipv4.value_as_string],
        )

        # ── 7. WAFの件数計測設定を作る補助関数 ──
        # メトリクスはAllowedRequests/CountedRequestsなどの時系列の件数です。
        # この関数はCDKの合成中に呼ばれ、各ルールの設定を返します。
        # AWS上でリクエストのたびに呼ばれるLambdaの関数とは別です。
        def visibility(name: str):
            return wafv2.CfnWebACL.VisibilityConfigProperty(
                cloud_watch_metrics_enabled=True,
                # WAFのサンプル表示は無効。後で有効にするリクエストログとは別機能です。
                sampled_requests_enabled=False,
                # CloudWatchでメトリクスを識別するための名前です。
                metric_name=name,
            )

        # ── 8. AWSが提供するルール集をCountで使う補助関数 ──
        # Managed Rule Groupは複数の検査ルールのセットです。
        # nameでルール集を選び、priorityでWeb ACL内の検査順序を指定します。
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
                # グループ内部の判定結果をCOUNTへ上書きし、後続の検査へ進めます。
                # 個別ルール全部をCountへ書き換える設定とは異なります。
                # グループ内部では最初の終端ルールに一致すると、そのグループの検査は止まります。
                # count={}の{}は「詳細オプションなしのCount」を表す指定で、件数の初期値ではありません。
                override_action=wafv2.CfnWebACL.OverrideActionProperty(
                    count={}
                ),
                visibility_config=visibility(name),
            )

        # ── 9. WAFの検査ルールをまとめたWeb ACLを定義 ──
        # Web ACLは検査ルール一覧です。作っただけではAPIに適用されず、手順10で関連付けます。
        # REGIONALはAPI Gatewayと同じリージョンで使う設定です。
        # CloudFront向けのCLOUDFRONTスコープとは異なります。
        web_acl = wafv2.CfnWebACL(
            self,
            "WebAcl",
            scope="REGIONAL",
            # 最後まで終端ルールに一致しなかったリクエストを許可します。
            # allow={}も「詳細オプションなしのAllow」を表します。
            default_action=wafv2.CfnWebACL.DefaultActionProperty(
                allow={}
            ),
            visibility_config=visibility("Lab01WebAcl"),
            # priorityの小さい順に評価します。Block/Allowは評価を終了し、
            # Countは一致を数えた後で後続ルールへ進みます。
            rules=[
                wafv2.CfnWebACL.RuleProperty(
                    # 先に「実験用IP以外」を遮断します。
                    # 実験用IPをAllowにすると後続のSQLi/XSS検査も終了するため、
                    # 許可IP自体には終端のAllowを設定しません。
                    name="BlockOutsideLab",
                    priority=0,
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        # NOT（IP Setに含まれる）＝IP Setに含まれない送信元に一致します。
                        not_statement=wafv2.CfnWebACL.NotStatementProperty(
                            statement=wafv2.CfnWebACL.StatementProperty(
                                ip_set_reference_statement=(
                                    wafv2.CfnWebACL.IPSetReferenceStatementProperty(
                                        # 上で定義したIP SetをARNで参照します。
                                        arn=allowed_ips.attr_arn
                                    )
                                ),
                            )
                        ),
                    ),
                    visibility_config=visibility("BlockOutsideLab"),
                ),
                wafv2.CfnWebACL.RuleProperty(
                    # 短時間に多数のリクエストを送る送信元IPを制限します。
                    # このルールはCountではなくBlockです。
                    name="RateLimit",
                    priority=10,
                    action=wafv2.CfnWebACL.RuleActionProperty(block={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        rate_based_statement=(
                            wafv2.CfnWebACL.RateBasedStatementProperty(
                                # 送信元IPごとに集計します。
                                aggregate_key_type="IP",
                                # 直近300秒（5分間）で300件を基準に制限します。
                                # 厳密に301件目で遮断されることを保証する設定ではありません。
                                limit=300,
                                evaluation_window_sec=300,
                            )
                        ),
                    ),
                    visibility_config=visibility("RateLimit"),
                ),
                # XSSなど、一般的なWeb攻撃の検査。結果をCountとして観察します。
                managed_rule("AWSManagedRulesCommonRuleSet", 20),
                # SQLインジェクションの検査。SQLを実行するのではなく、入力パターンを検査します。
                managed_rule("AWSManagedRulesSQLiRuleSet", 30),
                wafv2.CfnWebACL.RuleProperty(
                    name="LabMarker",
                    priority=40,
                    action=wafv2.CfnWebACL.RuleActionProperty(count={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        and_statement=wafv2.CfnWebACL.AndStatementProperty(
                            statements=[
                                wafv2.CfnWebACL.StatementProperty(
                                    byte_match_statement=(
                                        wafv2.CfnWebACL.ByteMatchStatementProperty(
                                            field_to_match=(
                                                wafv2.CfnWebACL.FieldToMatchProperty(
                                                    uri_path={}
                                                )
                                            ),
                                            positional_constraint="EXACTLY",
                                            search_string="/lab/search",
                                            text_transformations=[
                                                wafv2.CfnWebACL.TextTransformationProperty(
                                                    priority=0,
                                                    type="NONE",
                                                )
                                            ],
                                        )
                                    )
                                ),
                                wafv2.CfnWebACL.StatementProperty(
                                    byte_match_statement=(
                                        wafv2.CfnWebACL.ByteMatchStatementProperty(
                                            field_to_match=(
                                                wafv2.CfnWebACL.FieldToMatchProperty(
                                                    single_query_argument={"Name": "q"}
                                                )
                                            ),
                                            positional_constraint="EXACTLY",
                                            search_string="waf-lab-test",
                                            text_transformations=[
                                                wafv2.CfnWebACL.TextTransformationProperty(
                                                    priority=0,
                                                    type="NONE",
                                                )
                                            ],
                                        )
                                    )
                                ),
                            ]
                        ),
                    ),
                    visibility_config=visibility("LabMarker"),
                ),
                wafv2.CfnWebACL.RuleProperty(
                    name="CountAdmin",
                    priority=50,
                    action=wafv2.CfnWebACL.RuleActionProperty(count={}),
                    statement=wafv2.CfnWebACL.StatementProperty(
                        byte_match_statement=wafv2.CfnWebACL.ByteMatchStatementProperty(
                            field_to_match=wafv2.CfnWebACL.FieldToMatchProperty(
                                query_string={}
                            ),
                            positional_constraint="CONTAINS",
                            search_string="admin",
                            text_transformations=[
                                wafv2.CfnWebACL.TextTransformationProperty(
                                    priority=0,
                                    type="LOWERCASE",
                                )
                            ],
                        )
                    ),
                    visibility_config=visibility("CountAdmin"),
                ),
            ],
        )

        # ── 10. WAFをAPI Gatewayの公開ステージへ適用 ──
        # APIのlabステージとWeb ACLのARNを関連付けます。
        # これにより、そのステージへのリクエストがLambdaへ届く前に検査されます。
        # WAFを別のURLとしてブラウザから直接呼ぶ必要はありません。
        wafv2.CfnWebACLAssociation(
            self,
            "WebAclAssociation",
            resource_arn=api.deployment_stage.stage_arn,
            web_acl_arn=web_acl.attr_arn,
        )

        # ── 11. WAFのリクエストログを保存する設定 ──
        # ロググループを特定するARNを組み立てます。
        # partitionは通常aws、regionは東京、accountはデプロイ先アカウントです。
        # これらの値が合成時に未確定なら、CloudFormationで解決する参照になります。
        # WAFのログ出力先には末尾に :* が付かないロググループARNを渡します。
        waf_log_arn = (
            f"arn:{self.partition}:logs:{self.region}:{self.account}"
            f":log-group:{waf_logs.log_group_name}"
        )

        # 「どのWeb ACLの記録を、どの保存先へ送るか」を登録します。
        # ログフィルターを指定していないので、Allow/Block/Count一致のある記録を含めて保存します。
        # 最上位actionは最終動作なので、Count検知でもALLOWの場合があります。
        # 今回のCountは最上位nonTerminatingMatchingRulesのaction: COUNTを確認し、
        # ruleGroupList内でSQLi_QUERYARGUMENTSなどの個別ルールを調べます。
        # このログ設定と、手順7の件数メトリクス設定は別の機能です。
        wafv2.CfnLoggingConfiguration(
            self,
            "WafLogging",
            resource_arn=web_acl.attr_arn,
            log_destination_configs=[waf_log_arn],
        )

        # ── 12. デプロイ完了時に表示する情報 ──
        # Outputは確認用の出力欄で、新しいサーバーやAPIを作るものではありません。
        # ApiUrl：ブラウザやcurlでアクセスする /lab/ 付きのURLです。
        # WafLogGroupName：CloudWatch Logs Insightsで選択する保存先です。
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(
            self,
            "WafLogGroupName",
            value=waf_logs.log_group_name,
        )

        # 以下はcdk initで生成されたSQSの例です。全行コメントなので何も作成しません。
        # queue = sqs.Queue(
        #     self, "Lab01Queue",
        #     visibility_timeout=Duration.seconds(300),
        # )
