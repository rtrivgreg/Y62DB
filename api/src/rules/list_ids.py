"""GET /rules — list every rule ID that has at least one binding.

Powers the UI's client-side fuzzy rule-ID search: the browser fetches this
full list once, fuzzy-matches the user's query against it locally, then
fans out `GET /rules/{ruleId}/bindings` for each match. See
`common.dynamodb.list_distinct_rule_ids` for the scan + caveats.
"""
from common import dynamodb, response
from common.validation import Schema, validate

schema = Schema()


@validate(schema)
def handle(event, context, path_params=None, body=None):
    rule_ids = dynamodb.list_distinct_rule_ids()
    return response.success(200, data=rule_ids, meta_extra={"count": len(rule_ids)})
