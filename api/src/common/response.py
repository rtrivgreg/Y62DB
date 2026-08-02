"""Standardized API Gateway (Lambda proxy) response envelope.

Every response returned by this service — success or error — follows the
same shape so API consumers can write one deserialization path:

{
  "success": bool,
  "data": <object|array|null>,
  "error": { "code": str, "message": str, "details": object } | null,
  "meta": { "request_id": str, "timestamp": str, ...extra }
}
"""
import decimal
import json
import uuid
from datetime import datetime, timezone

DEFAULT_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}


class DecimalEncoder(json.JSONEncoder):
    """DynamoDB returns Decimal for numeric types; make them JSON-safe."""

    def default(self, obj):
        if isinstance(obj, decimal.Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def _meta(request_id: str, extra: dict = None) -> dict:
    payload = {
        "request_id": request_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if extra:
        payload.update(extra)
    return payload


def success(status_code: int, data=None, request_id: str = None, meta_extra: dict = None) -> dict:
    # 204 No Content must not carry a response body per RFC 7231.
    if status_code == 204:
        return {"statusCode": 204, "headers": DEFAULT_HEADERS, "body": ""}

    body = {
        "success": True,
        "data": data,
        "error": None,
        "meta": _meta(request_id or str(uuid.uuid4()), meta_extra),
    }
    return {
        "statusCode": status_code,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(body, cls=DecimalEncoder),
    }


def error(status_code: int, code: str, message: str, details: dict = None, request_id: str = None) -> dict:
    body = {
        "success": False,
        "data": None,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
        "meta": _meta(request_id or str(uuid.uuid4())),
    }
    return {
        "statusCode": status_code,
        "headers": DEFAULT_HEADERS,
        "body": json.dumps(body, cls=DecimalEncoder),
    }
