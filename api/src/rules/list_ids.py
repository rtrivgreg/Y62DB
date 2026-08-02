"""GET /rules — list every rule the UI needs to know about.

Returns the merged catalog + bindings view (see docs/BLUEPRINT.md §12.11):
every rule ID that has a seeded RULE_PROFILE catalog entry, every rule ID
that has at least one real binding, tagged with `has_binding`:

    [{"rule_id": "...", "has_binding": bool}, ...]

Powers two UI surfaces from one response: the rule-ID search box (client-
side substring match against the full merged list, so catalog-only rules
are discoverable too) and the Create Binding rule picker (so a binding can
be created for a rule that's never been bound). See
`common.dynamodb.list_all_rules_with_binding_status` for the scan + caveats.
"""
from common import dynamodb, response
from common.validation import Schema, validate

schema = Schema()


@validate(schema)
def handle(event, context, path_params=None, body=None):
    rules = dynamodb.list_all_rules_with_binding_status()
    return response.success(200, data=rules, meta_extra={"count": len(rules)})
