import csv
import json


def walk_statements(node):
    """AND・ORなどの内側も含めて、設定を順に調べる。"""
    if isinstance(node, dict):
        yield node

        for value in node.values():
            yield from walk_statements(value)

    elif isinstance(node, list):
        for value in node:
            yield from walk_statements(value)


def collect_references(client, web_acl):
    """Web ACLが参照するIPSetと管理ルールを取得する。"""
    ip_sets = []
    managed_groups = []

    # 同じIPSetが複数回参照されても、API取得は1回にする。
    ip_cache = {}
    group_cache = {}

    for parent_rule in web_acl.get("Rules", []):
        for statement in walk_statements(
            parent_rule["Statement"]
        ):
            if "IPSetReferenceStatement" in statement:
                reference = statement["IPSetReferenceStatement"]
                arn = reference["ARN"]

                if arn not in ip_cache:
                    # ARN末尾は ipset/名前/ID という形式。
                    _, name, resource_id = arn.rsplit("/", 2)

                    ip_cache[arn] = client.get_ip_set(
                        Name=name,
                        Id=resource_id,
                        Scope="REGIONAL",
                    )["IPSet"]

                ip_sets.append({
                    "parent_rule": parent_rule["Name"],
                    "reference": reference,
                    "ip_set": ip_cache[arn],
                })

            if "ManagedRuleGroupStatement" in statement:
                reference = statement["ManagedRuleGroupStatement"]

                params = {
                    "VendorName": reference["VendorName"],
                    "Name": reference["Name"],
                    "Scope": "REGIONAL",
                }

                # バージョン固定の場合は、同じバージョンを取得する。
                if reference.get("Version"):
                    params["VersionName"] = reference["Version"]

                cache_key = (
                    reference["VendorName"],
                    reference["Name"],
                    reference.get("Version"),
                )

                if cache_key not in group_cache:
                    response = client.describe_managed_rule_group(
                        **params
                    )
                    response.pop("ResponseMetadata", None)
                    group_cache[cache_key] = response

                managed_groups.append({
                    "parent_rule": parent_rule["Name"],
                    "group_override": parent_rule.get(
                        "OverrideAction", {}
                    ),
                    "reference": reference,
                    "description": group_cache[cache_key],
                })

    return {
        "ip_sets": ip_sets,
        "managed_groups": managed_groups,
    }


def write_csv(path, columns, rows):
    with path.open(
        "w", encoding="utf-8-sig", newline=""
    ) as file:
        writer = csv.DictWriter(file, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def save_references(
    output_dir, references, account_id, region, web_acl_name
):
    """取得した参照先をJSONとCSVへ保存する。"""
    common = {
        "account_id": account_id,
        "region": region,
        "web_acl_name": web_acl_name,
    }

    for filename, key in [
        ("ip-sets.json", "ip_sets"),
        ("managed-rule-groups.json", "managed_groups"),
    ]:
        document = {
            **common,
            "items": references[key],
        }

        (output_dir / filename).write_text(
            json.dumps(
                document, ensure_ascii=False, indent=2
            ) + "\n",
            encoding="utf-8",
        )

    ip_rows = []

    for item in references["ip_sets"]:
        ip_set = item["ip_set"]
        addresses = ip_set.get("Addresses", [])

        # 空のIPSetも、件数0の行として残す。
        for address in addresses or [""]:
            ip_rows.append({
                **common,
                "parent_rule": item["parent_rule"],
                "ip_set_name": ip_set["Name"],
                "ip_set_arn": ip_set["ARN"],
                "ip_version": ip_set["IPAddressVersion"],
                "address_count": len(addresses),
                "address": address,
            })

    write_csv(
        output_dir / "ip-addresses.csv",
        [
            *common,
            "parent_rule",
            "ip_set_name",
            "ip_set_arn",
            "ip_version",
            "address_count",
            "address",
        ],
        ip_rows,
    )

    managed_rows = []

    for item in references["managed_groups"]:
        reference = item["reference"]
        description = item["description"]

        # 個別ルールへの動作上書き。
        overrides = {
            entry["Name"]: next(
                iter(entry["ActionToUse"]), ""
            )
            for entry in reference.get(
                "RuleActionOverrides", []
            )
        }

        # 旧形式のCount指定も記録する。
        excluded = {
            entry["Name"]
            for entry in reference.get("ExcludedRules", [])
        }

        for rule in description.get("Rules", []):
            managed_rows.append({
                **common,
                "parent_rule": item["parent_rule"],
                "vendor": reference["VendorName"],
                "group_name": reference["Name"],
                "requested_version": reference.get(
                    "Version", "DEFAULT"
                ),
                "resolved_version": description.get(
                    "VersionName", ""
                ),
                "inner_rule_name": rule["Name"],
                "default_action": next(
                    iter(rule.get("Action", {})), ""
                ),
                "rule_action_override": overrides.get(
                    rule["Name"], ""
                ),
                "legacy_excluded_to_count": (
                    rule["Name"] in excluded
                ),
                "group_override": next(
                    iter(item["group_override"]), ""
                ),
            })

    write_csv(
        output_dir / "managed-rules.csv",
        [
            *common,
            "parent_rule",
            "vendor",
            "group_name",
            "requested_version",
            "resolved_version",
            "inner_rule_name",
            "default_action",
            "rule_action_override",
            "legacy_excluded_to_count",
            "group_override",
        ],
        managed_rows,
    )