"""GET /groups — list every group that has at least one binding.

Mirrors `rules.list_ids`, just for the group dimension — powers the UI's
fuzzy search when searching "By group" instead of "By rule ID". See
`common.dynamodb.list_distinct_groups` for the scan + caveats.
"""
from common import dynamodb, response
from common.validation import Schema, validate

schema = Schema()


@validate(schema)
def handle(event, context, path_params=None, body=None):
    groups = dynamodb.list_distinct_groups()
    return response.success(200, data=groups, meta_extra={"count": len(groups)})
