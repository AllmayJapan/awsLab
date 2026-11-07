# Lab01：WAF・API Gateway・LambdaによるWeb攻撃検知ラボ

Python CDKで構成を定義し、CloudFormationで作成・更新・削除する学習用ラボです。SQLi・XSSを模した少数のリクエストを送り、AWS WAFのCountとログを観察します。

アプリは入力をJSONで返すだけで、SQLや入力されたコードを実行しません。脆弱性の悪用ではなく、WAFのリクエスト検査を確認します。

更新日：2026年11月7日（日本時間）

## 1. 現在の到達点

- ユーザー確認済み：仮想環境の作成、CDK合成、主要リソースの確認、接続先アカウントの確認、差分確認、デプロイ。
- ユーザー確認済み：`/search?q=hello` が修正・再デプロイ後にHTTP 200を返す。
- 未確認：SQLi・XSS模擬リクエストの検知、Countメトリクス・WAFログの実測結果。
- 下記の中断・再開手順は運用手順であり、削除・再作成の実施記録ではありません。

## 2. 構成と設定

```text
実験用PC → API Gateway REST API → Lambda（Python）
                    ↑
           AWS WAFをステージに関連付け

WAF・API Gateway・Lambda → CloudWatch Logs
```

| 項目 | 設定 |
| --- | --- |
| 作業場所 | `/home/allmay/workspace/learning_aws/awsLab/labs/lab01` |
| Stack | `Lab01Stack` |
| AWSプロファイル | `default`（コマンドで明示） |
| リージョン | 東京 `ap-northeast-1`（`app.py` で指定） |
| APIステージ | `lab` |
| APIパス | `GET /`、`GET /search` |
| Lambda | Python 3.12、128 MB、タイムアウト5秒 |
| APIスロットリング | レート5リクエスト/秒、バースト10 |
| WAFログ | `aws-waf-logs-Lab01Stack` |
| ログ保存 | 7日。今回のロググループはStack削除時にも削除 |

WAFの評価順序：

| 優先順位 | ルール | 動作 |
| --- | --- | --- |
| 0 | `BlockOutsideLab`：許可IPv4以外 | Block |
| 10 | `RateLimit`：送信元IPごとに直近5分間で300件 | Block |
| 20 | `AWSManagedRulesCommonRuleSet` | グループの結果をCountに上書き |
| 30 | `AWSManagedRulesSQLiRuleSet` | グループの結果をCountに上書き |
| 最後 | デフォルト動作 | Allow |

実験用IPを先頭でAllowにすると後続の検査が実行されません。そのため、実験用IP「以外」をBlockにしています。レート制限は厳密に301件目を遮断する仕組みではありません。

## 3. ファイルの役割

```text
lab01/
├── app.py                  # Stackの起動・アカウントとリージョンの設定
├── cdk.json                # CDKの実行設定
├── requirements.txt        # CDK用のPython依存関係
├── requirements-dev.txt    # 開発用の依存関係
├── lab01/
│   ├── __init__.py
│   └── lab01_stack.py      # Lambda・API・WAF・ログの定義
├── application/
│   └── handler.py          # AWS上で実行するLambdaの処理
├── tests/                  # CDK生成のテスト用ひな型
├── .venv/                  # ローカル仮想環境（Git管理外）
└── cdk.out/                # 合成結果（自動生成・Git管理外）
```

`app.py` とStackのコードはUbuntu上で実行されます。`handler.py` はLambdaにアップロードされ、AWS上で実行されます。`cdk.out/` のCloudFormationを直接編集せず、元のPythonコードを修正します。

Gitにはソース・設定・READMEを保存します。`.venv/`、`cdk.out/`、`__pycache__/`、認証情報は保存しません。`cdk.context.json` が生成された場合は、通常はGitで管理します。

## 4. 初回構築

### 4.1 プロジェクト生成と仮想環境

以下は新規作成時の記録です。既存のlab01では `cdk init` を再実行しません。

空の実験ディレクトリで実行します。

```bash
cdk init app --language python --generate-only
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

`--generate-only` では仮想環境の作成も省略されるため、手動で作成します。

`application/handler.py` を追加し、`lab01/lab01_stack.py` にリソースを定義、`app.py` で `Lab01Stack` を起動します。実際の定義は各ソースファイルを参照してください。

### 4.2 合成と主要リソースの確認

```bash
cd /home/allmay/workspace/learning_aws/awsLab/labs/lab01
source .venv/bin/activate
cdk list
cdk synth
```

`Lab01Stack` が表示され、`cdk.out/Lab01Stack.template.json` が生成されることを確認します。

```bash
python - <<'PY'
import json
from collections import Counter

with open("cdk.out/Lab01Stack.template.json") as f:
    template = json.load(f)
for resource_type, count in sorted(Counter(
    resource["Type"] for resource in template["Resources"].values()
).items()):
    print(f"{resource_type}: {count}")
PY
```

Lambda、API Gateway、WAFのIPSet・WebACL・WebACLAssociation・LoggingConfiguration、CloudWatchのLogGroupが含まれることを確認します。合成だけではAWSリソースは作成されません。

### 4.3 プロファイル・接続先・準備状況

```bash
aws configure list-profiles
aws configure list --profile default
aws sts get-caller-identity --profile default
```

`Account` が学習用アカウント、`Arn` が想定する実行者であることを確認します。接続成功だけではデプロイ権限を保証しません。IAMのユーザー・ロール・所属グループの許可も確認します。AdministratorAccessがあっても組織側の制限などで拒否される場合があります。

```bash
aws cloudformation describe-stacks \
  --stack-name CDKToolkit \
  --profile default \
  --region ap-northeast-1 \
  --query 'Stacks[0].StackStatus' \
  --output text
```

`CREATE_COMPLETE`・`UPDATE_COMPLETE` なら準備用Stackが存在します。Stackが存在しない場合は、接続先を確認してbootstrapします。AccessDeniedは「存在しない」という意味ではありません。

次の `123456789012` は、確認した自分のアカウントIDに置き換えます。

```bash
cdk bootstrap aws://123456789012/ap-northeast-1 --profile default
```

bootstrapはS3バケットやIAMロールなどを作成する初期準備です。通常はアカウント・リージョンごとに実施し、実験のたびに作り直しません。

### 4.4 差分確認とデプロイ

```bash
cdk diff Lab01Stack --profile default --no-change-set
curl -4 https://checkip.amazonaws.com
```

初回の差分は基本的に追加です。`[+]` は追加、`[-]` は削除、`[~]` は変更です。`--no-change-set` は変更セットを作らずに比較するモードで、置換判定の精度には制約があります。

以下の `203.0.113.10` は例示用です。表示された実際のグローバルIPv4に置き換え、1アドレスだけを表す `/32` を付けて指定します。

```bash
cdk deploy Lab01Stack \
  --profile default \
  --parameters "Lab01Stack:AllowedIpv4=203.0.113.10/32"
```

変更内容を確認し、承認を求められた場合は内容に問題がなければ `y` を入力します。ここからAWSリソースが作成され、WAFなどの料金が発生します。

完了時のOutputsにある `ApiUrl` と `WafLogGroupName` を確認します。

## 5. 正常通信と模擬攻撃の実験

### 5.1 API URLを設定

以下のURLは例です。デプロイ完了時の `ApiUrl` に置き換えてください。再作成するとURLが変わります。末尾の `/` も含めます。

```bash
LAB01_API_URL='https://YOUR_API_ID.execute-api.ap-northeast-1.amazonaws.com/lab/'
curl -i "$LAB01_API_URL"
```

HTTP 200とHTMLが返ることを確認します。以降は許可済みの同じUbuntuから1件ずつ実行します。

### 5.2 正常リクエスト

```bash
curl -i -G "${LAB01_API_URL}search" \
  --data-urlencode 'q=hello' \
  --data-urlencode 'labcase=normal01'
```

期待する本文：`{"message": "Search request received", "q": "hello"}`。

### 5.3 SQLiを模したリクエスト

```bash
curl -i -G "${LAB01_API_URL}search" \
  --data-urlencode "q=' OR 1=1 --" \
  --data-urlencode 'labcase=sqli01'
```

### 5.4 XSSを模したリクエスト

```bash
curl -i -G "${LAB01_API_URL}search" \
  --data-urlencode 'q=<script>alert(1)</script>' \
  --data-urlencode 'labcase=xss01'
```

`-G` はGET、`--data-urlencode` は記号や空白のURLエンコードを指定します。`labcase` はログ検索用の目印です。繰り返す場合は値を変えるか実行時刻で区別します。

Count設定では検知されても通常HTTP 200が返ります。200だけでは検知の有無は判断できません。

## 6. WAFのログとCountを確認

### 6.1 CloudWatch Logs Insights

AWSコンソールで東京リージョンのCloudWatch → Logs Insightsを開き、`aws-waf-logs-Lab01Stack` を選びます。時間範囲を直近30分など実験時刻を含む範囲にして実行します。

```text
fields @timestamp, httpRequest.clientIp, httpRequest.args,
       action, terminatingRuleId, @message
| filter httpRequest.args like /labcase=/
| sort @timestamp desc
| limit 30
```

ログの反映には時間がかかる場合があります。見つからなければ数分後に再実行します。

| 項目 | 確認内容 |
| --- | --- |
| `httpRequest.args` | 送信した `labcase` |
| 最上位の `action` | WAFの最終動作。今回のCount実験では通常 `ALLOW` |
| `terminatingRuleId` | デフォルトで許可した場合は通常 `Default_Action` |
| `nonTerminatingMatchingRules` | 検査を終了しなかった一致情報 |
| `ruleGroupList` | グループ内部の一致ルールと判定 |
| `labels` | 一致したルールが付けたラベル |

`@message` を展開して確認します。最上位の `action = "COUNT"` だけでは検索しません。

現在はグループの結果をCountに上書きしています。グループ内部の `terminatingRule.action` が `BLOCK` でも、リクエスト全体を遮断したとは限りません。最上位の動作と、グループ内の判定を区別します。グループ内部では最初の終端ルールで評価が止まるため、全ルールの一致を網羅する設定ではありません。

SQLiの `SQLi_QUERYARGUMENTS`、XSSの `CrossSiteScripting_QUERYARGUMENTS` などが観測候補ですが、実際の一致名と結果を記録します。200でも一致情報がなければ、検知は確認できていません。

### 6.2 Countメトリクス

CloudWatch → メトリクス → すべてのメトリクス → `AWS/WAFV2` を開きます。対象Web ACLとManaged Rule Groupを参照するルールに対応する `CountedRequests` を探します。

統計は合計（Sum）、期間は1分、表示時間は実験時刻を含む範囲にします。グループのCount上書きと、個別ルールのCountは区別します。まずログの実測を確認し、メトリクスの反映も待って確認します。

`sampled_requests_enabled=False` のため、Sampled requestsには頼らず、CloudWatchのリクエストログで確認します。

### 6.3 実験記録

| 実行日時（JST） | labcase | HTTP応答 | 一致ルール | WAF最終動作 | 備考 |
| --- | --- | --- | --- | --- | --- |
| 未記録 | normal01 | 未記録 | 未記録 | 未記録 | 正常通信 |
| 未記録 | sqli01 | 未記録 | 未記録 | 未記録 | SQLi模擬 |
| 未記録 | xss01 | 未記録 | 未記録 | 未記録 | XSS模擬 |

## 7. ソース修正後の更新

```bash
cd /home/allmay/workspace/learning_aws/awsLab/labs/lab01
source .venv/bin/activate
cdk diff Lab01Stack --profile default --no-change-set
cdk deploy Lab01Stack --profile default
```

通常は削除せず同じStackを更新します。`Code.from_asset()` により `application/` 内のコード変更もアップロードされます。diff・deployで合成されるため、毎回synthを別途実行する必要はありません。

通常の更新では前回の `AllowedIpv4` が引き継がれます。送信元IPが変わった場合は、現在のIPv4を `/32` 付きで再指定します。デプロイ後は同じリクエストを再送して動作確認します。

## 8. 中断する

### 8.1 短い休憩：ラボを残す

ソースを保存して、`deactivate` を実行しターミナルを閉じます。ローカルの仮想環境を終了してもAWS上のリソースは残り、WAFなどの料金も継続します。

### 8.2 しばらく使わない：ラボを削除する

1. 必要なWAFログや実験結果をローカルに保存します。CloudWatchの検索結果は画面からダウンロードして保存できます。
2. ソースを保存し、Gitを利用していれば差分を確認してコミットします。
3. 以下を実行して削除確認に応答し、完了まで確認します。

```bash
cd /home/allmay/workspace/learning_aws/awsLab/labs/lab01
source .venv/bin/activate
cdk destroy Lab01Stack --profile default
```

今回のロググループも削除されます。`CDKToolkit` と、そのS3バケットにアップロード済みのアセットは別管理で残ります。ラボ削除がアカウント全体の料金ゼロを意味するわけではありません。

Stackが削除されたことは、CloudFormationコンソールでも確認します。ソースと `.venv/` はローカルに残ります。

```bash
deactivate
```

## 9. 再開する

```bash
cd /home/allmay/workspace/learning_aws/awsLab/labs/lab01
source .venv/bin/activate
aws sts get-caller-identity --profile default
curl -4 https://checkip.amazonaws.com
```

認証期限切れの場合は、設定済みの認証方法で接続を回復してから進めます。

- ラボを残し、送信元IPも同じ：再デプロイせず、既存URLへアクセスします。
- ラボを残したがIPが変わった：現在のIPを指定して更新します。
- ラボを削除した：現在のIPを指定して再作成します。

後者2つの場合は、以下の例示用IPを現在の値に置き換えます。

```bash
cdk diff Lab01Stack --profile default --no-change-set
cdk deploy Lab01Stack \
  --profile default \
  --parameters "Lab01Stack:AllowedIpv4=203.0.113.10/32"
```

再作成後はOutputsの新しい `ApiUrl` を使い、セクション5の `LAB01_API_URL` を設定し直します。通常はvenv作成・依存インストール・bootstrapのやり直しは不要です。依存を変更した場合は `python -m pip install -r requirements.txt` を実行します。

## 10. トラブルシューティング

| 症状 | 原因・対応 |
| --- | --- |
| `.venv/bin/activate` がない | プロジェクトの場所を確認。未作成なら `python3 -m venv .venv`。`--generate-only` では自動作成されない |
| `json_with_standard_fields()` のTypeError | `caller`、`http_method`、`ip`、`protocol`、`request_time`、`resource_path`、`response_length`、`status`、`user` の9項目を明示する |
| `/search` がHTTP 502 | 今回は `StatusCode` の誤記を `statusCode` に修正して再デプロイし、200を確認。他の502はLambdaのログと応答形式を調べる |
| HTTP 403 | WAFログの `terminatingRuleId` と送信元IPを確認。送信元制限・レート制限・設定反映待ちを切り分ける |
| HTTP 429 | API Gatewayなどのスロットリングを確認。少数のリクエストを間隔を空けて送る |
| 200だがCountが確認できない | 200だけでは検知の証拠にならない。WAFログのグループ内判定とラベルを確認する |
| ログが見つからない | 東京リージョン・ロググループ・時間範囲・ログ反映待ちを確認する |

## 11. 公式資料

- [CDK Pythonプロジェクト](https://docs.aws.amazon.com/cdk/v2/guide/work-with-cdk-python.html)
- [CDK bootstrap](https://docs.aws.amazon.com/cdk/v2/guide/bootstrapping.html)
- [cdk diff](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-diff.html)
- [cdk deploy](https://docs.aws.amazon.com/cdk/v2/guide/ref-cli-cmd-deploy.html)
- [CloudFormationパラメータ](https://docs.aws.amazon.com/cdk/v2/guide/get-cfn-param.html)
- [API GatewayとWAF](https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-control-access-aws-waf.html)
- [WAFログの項目](https://docs.aws.amazon.com/waf/latest/developerguide/logging-fields.html)
- [WAFルールグループのCount上書き](https://docs.aws.amazon.com/waf/latest/developerguide/web-acl-rule-group-override-options.html)
- [API GatewayとLambdaのエラー](https://docs.aws.amazon.com/lambda/latest/dg/services-apigateway-errors.html)
- [WAF料金](https://aws.amazon.com/waf/pricing/)
