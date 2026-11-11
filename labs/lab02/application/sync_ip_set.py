import ipaddress
import json
import logging
import os

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def validate_addresses(document):
    if not isinstance(document, dict):
        raise ValueError("JSON must be an object")

    addresses = document.get("addresses")
    if not isinstance(addresses, list):
        raise ValueError("addresses must be a list")

    validated = set()

    for address in addresses:
        if not isinstance(address, str) or "/" not in address:
            raise ValueError(f"CIDR notation required: {address!r}")

        network = ipaddress.ip_network(address, strict=True)

        if network.version != 4 or network.prefixlen == 0:
            raise ValueError(f"Unsupported IPv4 CIDR: {address!r}")

        validated.add(str(network))

    if len(validated) > 10000:
        raise ValueError("Too many addresses")

    return sorted(validated)


def handler(event, context):
    s3 = boto3.client("s3")
    waf = boto3.client("wafv2")

    # イベントの発生時点ではなく、現在のファイルを読み取る。
    response = s3.get_object(
        Bucket=os.environ["IP_LIST_BUCKET"],
        Key=os.environ["IP_LIST_KEY"],
    )

    with response["Body"] as body:
        document = json.loads(body.read().decode("utf-8"))

    # 全件の検証が成功してからWAFを更新する。
    addresses = validate_addresses(document)

    ip_set_params = {
        "Name": os.environ["IP_SET_NAME"],
        "Id": os.environ["IP_SET_ID"],
        "Scope": "REGIONAL",
    }

    for attempt in range(3):
        current = waf.get_ip_set(**ip_set_params)

        try:
            waf.update_ip_set(
                **ip_set_params,
                Description=current["IPSet"].get("Description", ""),
                Addresses=addresses,
                LockToken=current["LockToken"],
            )
            break
        except waf.exceptions.WAFOptimisticLockException:
            if attempt == 2:
                raise

    logger.info("IPSet synchronized: address_count=%d", len(addresses))
    return {"address_count": len(addresses)}