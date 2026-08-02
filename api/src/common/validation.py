"""Lightweight validation middleware.

Keeps the project dependency-free (no `jsonschema`) while still giving each
route a declarative way to describe what a valid request looks like. A
resource module builds a `Schema` and wraps its handler function with
`validate(schema)`; the decorator raises `ValidationError` on the first
violation, which the router in `handler.py` turns into a 400 response.
"""
import json
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Optional

from common.exceptions import ValidationError

_TYPE_MAP = {
    "string": str,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


@dataclass
class Field:
    name: str
    type: str = "string"
    required: bool = False
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    allowed_values: Optional[list] = None


@dataclass
class Schema:
    """Describes required path params and an optional JSON body shape."""

    path_params: list = field(default_factory=list)
    body_fields: list = field(default_factory=list)
    require_body: bool = False


def _validate_path_params(event: dict, required: list):
    path_params = event.get("pathParameters") or {}
    missing = [name for name in required if not path_params.get(name)]
    if missing:
        raise ValidationError(
            "Missing required path parameter(s).",
            details={"missing_path_params": missing},
        )
    return path_params


def _parse_body(event: dict, require_body: bool) -> dict:
    raw_body = event.get("body")
    if raw_body is None or raw_body == "":
        if require_body:
            raise ValidationError("Request body is required.")
        return {}
    try:
        parsed = json.loads(raw_body)
    except (json.JSONDecodeError, TypeError):
        raise ValidationError("Request body must be valid JSON.")
    if not isinstance(parsed, dict):
        raise ValidationError("Request body must be a JSON object.")
    return parsed


def _validate_field(field_def: Field, value: Any, errors: list):
    if value is None:
        if field_def.required:
            errors.append(f"'{field_def.name}' is required.")
        return

    expected_type = _TYPE_MAP.get(field_def.type, str)
    if not isinstance(value, expected_type):
        errors.append(f"'{field_def.name}' must be of type {field_def.type}.")
        return

    if field_def.type == "string":
        if field_def.min_length is not None and len(value) < field_def.min_length:
            errors.append(f"'{field_def.name}' must be at least {field_def.min_length} characters.")
        if field_def.max_length is not None and len(value) > field_def.max_length:
            errors.append(f"'{field_def.name}' must be at most {field_def.max_length} characters.")

    if field_def.allowed_values is not None and value not in field_def.allowed_values:
        errors.append(f"'{field_def.name}' must be one of {field_def.allowed_values}.")


def _validate_body(body: dict, fields: list) -> dict:
    errors = []
    for field_def in fields:
        _validate_field(field_def, body.get(field_def.name), errors)
    if errors:
        raise ValidationError("One or more fields failed validation.", details={"fields": errors})
    return body


def validate(schema: Schema) -> Callable:
    """Decorator: validates path params + body against `schema` before the
    wrapped resource function runs. Injects `path_params` and `body` kwargs.
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(event: dict, context, **kwargs):
            path_params = _validate_path_params(event, schema.path_params)
            body = _parse_body(event, schema.require_body)
            if schema.body_fields:
                body = _validate_body(body, schema.body_fields)
            return func(event, context, path_params=path_params, body=body, **kwargs)

        return wrapper

    return decorator
