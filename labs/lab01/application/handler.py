import json

def handler(event, context):
    path = event.get("path", "/")

    if path == "/":
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/html; charset=utf-8",
            },
            "body": "<h1>Lab01</h1><p>WAF experiment application</p>",
        }

    if path == "/search":
        query = event.get("queryStringParameters") or {}

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json; charset=utf-8",
            },
            "body": json.dumps(
                {"message": "Search request received", "q": query.get("q","")},
                ensure_ascii=False,
            ),
        }
    return {
        "statusCode": 404,
        "body": "Not Found",
    }