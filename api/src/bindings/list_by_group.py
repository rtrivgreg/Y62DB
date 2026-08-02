"""GET /groups/{group}/bindings — list every rule bound to a group (via gsi1)."""
from common import dynamodb, response
from common.validation import Schema, validate

schema = Schema(path_params=["group"])


@validate(schema)
def handle(event, context, path_params=None, body=None):
    query = event.get("queryStringParameters") or {}
    limit = int(query.get("limit", 20))
    cursor = query.get("cursor")

    result = dynamodb.list_bindings_for_group(path_params["group"], limit=limit, cursor=cursor)
    return response.success(
        200,
        data=result["items"],
        meta_extra={"count": result["count"], "next_cursor": result["next_cursor"]},
    )
