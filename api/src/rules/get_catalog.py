"""GET /rules/{ruleId}/catalog — full catalog entry for one rule.

Lets the UI let a user drill into a rule (from the search results or the
Create Binding picker) to see its description, severity, scopes, and full
PARAMETER_DEF set before creating a binding. See docs/BLUEPRINT.md §12.11.

404s for rules that only exist because they have a binding but were never
seeded into the catalog (e.g. the QA test artifacts like "a2_1") — there's
no catalog data to show for those.
"""
from common import dynamodb, response
from common.validation import Schema, validate

schema = Schema(path_params=["ruleId"])


@validate(schema)
def handle(event, context, path_params=None, body=None):
    catalog_entry = dynamodb.get_rule_catalog(path_params["ruleId"])
    return response.success(200, data=catalog_entry)
