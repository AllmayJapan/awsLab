import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.config import Config

from collect import save_inventory
from references import (
    collect_references,
    save_references,
    write_csv,
)


def list_web_acls(client):
    """REGIONALのWeb ACLを全ページ取得する。"""
    items = []
    params = {"Scope": "REGIONAL"}

    while True:
        response = client.list_web_acls(**params)
        items.extend(response.get("WebACLs", []))

        marker = response.get("NextMarker")
        if not marker:
            return items

        params["NextMarker"] = marker


def merge_csv(directories, filename, destination):
    """成功したWAFのCSVを1つにまとめる。"""
    columns = None
    rows = []

    for directory in directories:
        with (directory / filename).open(
            encoding="utf-8-sig", newline=""
        ) as file:
            reader = csv.DictReader(file)

            if columns is None:
                columns = reader.fieldnames
            elif columns != reader.fieldnames:
                raise ValueError(
                    f"CSVの列が一致しません: {filename}"
                )

            rows.extend(reader)

    if columns is not None:
        write_csv(destination, columns, rows)


def main():
    parser = argparse.ArgumentParser(
        description="複数アカウントのWAFを収集します。"
    )
    parser.add_argument(
        "--targets", type=Path, default=Path("targets.json")
    )
    args = parser.parse_args()

    targets = json.loads(
        args.targets.read_text(encoding="utf-8")
    )
    if not isinstance(targets, list) or not targets:
        raise ValueError("targets.jsonには対象一覧を指定してください")

    timestamp = datetime.now(timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    run_dir = (
        Path(__file__).resolve().parent
        / "output"
        / f"multi-{timestamp}"
    )
    run_dir.mkdir(parents=True, exist_ok=False)

    results = []
    successful_dirs = []

    for index, target in enumerate(targets, start=1):
        result = {
            "target_index": index,
            "profile": target["profile"],
            "expected_account_id": target["account_id"],
            "actual_account_id": "",
            "region": target["region"],
            "web_acl_name": "",
            "status": "",
            "error": "",
            "output_dir": "",
        }

        try:
            session = boto3.Session(
                profile_name=target["profile"],
                region_name=target["region"],
            )
            account_id = session.client(
                "sts"
            ).get_caller_identity()["Account"]
            result["actual_account_id"] = account_id

            if account_id != target["account_id"]:
                raise ValueError(
                    "接続先アカウントが設定と一致しません"
                )

            client = session.client(
                "wafv2",
                config=Config(
                    retries={
                        "mode": "standard",
                        "max_attempts": 5,
                    }
                ),
            )

            summaries = list_web_acls(client)

            if not summaries:
                results.append({
                    **result,
                    "status": "NO_WEB_ACLS",
                })
                continue

            for summary in summaries:
                item_result = {
                    **result,
                    "web_acl_name": summary["Name"],
                }

                try:
                    web_acl = client.get_web_acl(
                        Name=summary["Name"],
                        Id=summary["Id"],
                        Scope="REGIONAL",
                    )["WebACL"]

                    references = collect_references(
                        client, web_acl
                    )

                    output_dir = (
                        run_dir
                        / f"target-{index:03d}"
                        / account_id
                        / target["region"]
                        / web_acl["Id"]
                    )

                    save_inventory(
                        web_acl,
                        account_id,
                        target["region"],
                        output_dir=output_dir,
                    )
                    save_references(
                        output_dir,
                        references,
                        account_id,
                        target["region"],
                        web_acl["Name"],
                    )

                    successful_dirs.append(output_dir)
                    item_result.update({
                        "status": "OK",
                        "output_dir": str(
                            output_dir.relative_to(run_dir)
                        ),
                    })

                except Exception as error:
                    item_result.update({
                        "status": "FAILED",
                        "error": str(error),
                    })

                results.append(item_result)

        except Exception as error:
            results.append({
                **result,
                "status": "FAILED",
                "error": str(error),
            })

    write_csv(
        run_dir / "collection-status.csv",
        [
            "target_index",
            "profile",
            "expected_account_id",
            "actual_account_id",
            "region",
            "web_acl_name",
            "status",
            "error",
            "output_dir",
        ],
        results,
    )

    for filename in [
        "rules.csv",
        "ip-addresses.csv",
        "managed-rules.csv",
    ]:
        merge_csv(
            successful_dirs,
            filename,
            run_dir / f"all-{filename}",
        )

    failed = sum(
        item["status"] == "FAILED" for item in results
    )
    print(f"保存先: {run_dir}")
    print(f"取得成功Web ACL数: {len(successful_dirs)}")
    print(f"失敗件数: {failed}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()