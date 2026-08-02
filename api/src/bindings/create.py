"""POST /rules/{ruleId}/bindings — bind a rule's configuration to a group.

Body: { "group": "corp", "binding": "default", "payload": { "status": "ACTIVE", "version": 1, ... } }
`binding` defaults to "default" when omitted (most rules only need one
configuration per group). `payload` holds rule-specific parameters (e.g.
`maxAccessKeyAge` for access-keys-rotated) and is intentionally open-ended —
only `status` and `version` are enforced here since they're common to every
rule's payload in this catalog.
"""
from common import dynamodb, response
from common.exceptions import ValidationError
from common.validation import Field, Schema, validate

schema = Schema(
    path_params=["ruleId"],
    require_body=True,
    body_fields=[
        Field(name="group", type="string", required=True, min_length=1, max_length=100),
        Field(name="binding", type="string", required=False, min_length=1, max_length=100),
        Field(name="payload", type="object", required=True),
    ],
)

ALLOWED_STATUSES = ["ACTIVE", "INACTIVE"]


def _validate_payload(payload: dict):
    errors = []
    if "status" not in payload:
        errors.append("'payload.status' is required.")
    elif payload["status"] not in ALLOWED_STATUSES:
        errors.append(f"'payload.status' must be one of {ALLOWED_STATUSES}.")
    if "version" not in payload:
        errors.append("'payload.version' is required.")
    elif not isinstance(payload["version"], (int, float)):
        errors.append("'payload.version' must be a number.")
    if errors:
        raise ValidationError("Payload failed validation.", details={"fields": errors})


@validate(schema)
def handle(event, context, path_params=None, body=None):
    _validate_payload(body["payload"])
    binding = body.get("binding") or dynamodb.DEFAULT_BINDING
    item = dynamodb.create_binding(path_params["ruleId"], body["group"], binding, body["payload"])
    return response.success(201, data=item)
