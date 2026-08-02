"""DELETE /rules/{ruleId}/bindings/{group}/{binding} — remove a binding."""
from common import dynamodb, response
from common.validation import Schema, validate

schema = Schema(path_params=["ruleId", "group", "binding"])


@validate(schema)
def handle(event, context, path_params=None, body=None):
    dynamodb.delete_binding(path_params["ruleId"], path_params["group"], path_params["binding"])
    return response.success(204, data=None)
