import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from references import collect_references, save_references

import boto3
from botocore.config import Config


def find_web_acl(client, name):
    """名前が一致するWeb ACLを探す。"""
    params = {"Scope": "REGIONAL"}

    while True:
        response = client.list_web_acls(**params)

        for item in response.get("WebACLs", []):
            if item["Name"] == name:
                return client.get_web_acl(
                    Name=item["Name"],
                    Id=item["Id"],
                    Scope="REGIONAL",
                )["WebACL"]

        # AWSの一覧が複数ページに分かれている場合は続きを取得する。
        marker = response.get("NextMarker")
        if not marker:
            break

        params["NextMarker"] = marker

    raise RuntimeError(
        f"Web ACLが見つかりません: {name}"
    )


def save_inventory(web_acl, account_id, region, output_dir=None):
    """JSONとCSVを、実行日時ごとのフォルダーへ保存する。"""
    collected_at = datetime.now(timezone.utc)

    if output_dir is None:

        folder_name = collected_at.strftime("%Y%m%dT%H%M%S%fZ")
        output_dir = (
            Path(__file__).resolve().parent
            / "output"
            / folder_name
        )

    output_dir.mkdir(parents=True, exist_ok=False)

    # AWSから取得したWeb ACLの設定を、そのまま残す。
    document = {
        "collected_at": collected_at.isoformat(),
        "account_id": account_id,
        "region": region,
        "scope": "REGIONAL",
        "web_acl": web_acl,
    }

    json_path = output_dir / "web-acl.json"
    json_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    # 見やすい一覧として、Web ACL直下の1ルールを1行にする。
    columns = [
        "account_id",
        "region",
        "web_acl_name",
        "priority",
        "rule_name",
        "action",
        "group_override",
        "statement_type",
        "statement_json",
    ]

    csv_path = output_dir / "rules.csv"

    # Excelでも日本語を開きやすい形式。
    with csv_path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()

        for rule in sorted(
            web_acl.get("Rules", []),
            key=lambda item: item["Priority"],
        ):
            statement = rule["Statement"]

            writer.writerow({
                "account_id": account_id,
                "region": region,
                "web_acl_name": web_acl["Name"],
                "priority": rule["Priority"],
                "rule_name": rule["Name"],
                "action": next(
                    iter(rule.get("Action", {})), "RULE_GROUP"
                ),
                "group_override": next(
                    iter(rule.get("OverrideAction", {})), ""
                ),
                "statement_type": next(iter(statement), ""),
                "statement_json": json.dumps(
                    statement, ensure_ascii=False
                ),
            })

    return json_path, csv_path


def main():
    parser = argparse.ArgumentParser(
        description="Lab02のWAF設定をJSONとCSVへ保存します。"
    )
    parser.add_argument("--profile", required=True)
    parser.add_argument(
        "--region", default="ap-northeast-1"
    )
    parser.add_argument(
        "--web-acl-name", default="lab02-web-acl"
    )
    args = parser.parse_args()

    session = boto3.Session(
        profile_name=args.profile,
        region_name=args.region,
    )
    account_id = session.client(
        "sts"
    ).get_caller_identity()["Account"]

    client = session.client(
        "wafv2",
        config=Config(
            retries={"mode": "standard", "max_attempts": 5}
        ),
    )

    print(f"取得先: account={account_id}, region={args.region}")

    web_acl = find_web_acl(client, args.web_acl_name)

    references = collect_references(client, web_acl)

    json_path, csv_path = save_inventory(
        web_acl, account_id, args.region
    )

    save_references(
        json_path.parent,
        references,
        account_id,
        args.region,
        web_acl["Name"],
    )

    print(f"Web ACL: {web_acl['Name']}")
    print(f"ルール数: {len(web_acl.get('Rules', []))}")
    print(f"JSON: {json_path}")
    print(f"CSV : {csv_path}")
    print(f"参照IPSet数: {len(references['ip_sets'])}")
    print(f"管理ルールグループ数: {len(references['managed_groups'])}")
    print(f"保存先: {json_path.parent}")


if __name__ == "__main__":
    main()