"""PUT /rules/{ruleId}/bindings/{group}/{binding} — replace a binding's payload.

Uses optimistic locking, per the catalog's suggested access patterns: the
caller must include `expected_version`, the version they last read for this
binding. The write is rejected with 409 if the stored version has since
moved on (someone else updated it first), so concurrent editors can't
silently clobber each other's changes.

Body: { "payload": { "status": ..., "version": <new version>, ... }, "expected_version": <version last read> }
"""
from common import dynamodb, response
from common.exceptions import ValidationError
from common.validation import Field, Schema, validate
from bindings.create import _validate_payload

schema = Schema(
    path_params=["ruleId", "group", "binding"],
    require_body=True,
    body_fields=[
        Field(name="payload", type="object", required=True),
        Field(name="expected_version", type="number", required=True),
    ],
)


@validate(schema)
def handle(event, context, path_params=None, body=None):
    _validate_payload(body["payload"])
    item = dynamodb.update_binding(
        path_params["ruleId"],
        path_params["group"],
        path_params["binding"],
        body["payload"],
        body["expected_version"],
    )
    return response.success(200, data=item)
