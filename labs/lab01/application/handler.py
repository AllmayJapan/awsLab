import json
from pathlib import Path


def handler(event, context):
    path = event.get("path", "/")

    if path == "/":
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/html; charset=utf-8",
                "Cache-Control": "no-store",
            },
            "body": Path(__file__).with_name("index.html").read_text(
                encoding="utf-8"
            ),
        }

    if path == "/search":
        query = event.get("queryStringParameters") or {}
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json; charset=utf-8",
                "Cache-Control": "no-store",
            },
            "body": json.dumps(
                {
                    "message": "Search request received",
                    "q": query.get("q", ""),
                    "labcase": query.get("labcase", ""),
                },
                ensure_ascii=False,
            ),
        }

    return {"statusCode": 404, "body": "Not Found"}
