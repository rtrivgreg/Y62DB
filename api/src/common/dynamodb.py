"""DynamoDB access layer for the `y62db-config-rule-catalog` table.

This table uses a single-table design (already seeded, not created by this
project's Terraform):

    pk      = "RULE#<ruleId>"
    sk      = "GROUP#<group>#BINDING#<binding>"
    gsi1pk  = "GROUP#<group>"                        (GSI: gsi1)
    gsi1sk  = "RULE#<ruleId>#BINDING#<binding>"
    payload = { ...rule-specific config, e.g. maxAccessKeyAge, status, version }

A "binding" is one AWS Config managed rule's configuration as applied to one
group (e.g. business unit / account group). One rule can have many bindings
(one per group), and one group can have many rule bindings — hence the GSI,
which lets you query "everything bound to group X" as well as "everything
bound to rule Y".
"""
import os
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError

from common.exceptions import ConflictError, NotFoundError

TABLE_NAME = os.environ.get("CONFIG_RULE_CATALOG_TABLE", "y62db-config-rule-catalog")
GSI1_NAME = os.environ.get("CONFIG_RULE_CATALOG_GSI1", "gsi1")
DEFAULT_BINDING = "default"

_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(TABLE_NAME)


def _pk(rule_id: str) -> str:
    return f"RULE#{rule_id}"


def _sk(group: str, binding: str) -> str:
    return f"GROUP#{group}#BINDING#{binding}"


def _gsi1pk(group: str) -> str:
    return f"GROUP#{group}"


def _gsi1sk(rule_id: str, binding: str) -> str:
    return f"RULE#{rule_id}#BINDING#{binding}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _to_binding_view(item: dict) -> dict:
    """Strip the internal key-overloading attributes out of the raw DynamoDB
    item and present a clean resource representation to API consumers."""
    rule_id = item["pk"].split("RULE#", 1)[1]
    _, group, _, binding = item["sk"].split("#")
    return {
        "rule_id": rule_id,
        "group": group,
        "binding": binding,
        "payload": item.get("payload", {}),
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
    }


def list_bindings_for_rule(rule_id: str, limit: int = 20, cursor: str = None) -> dict:
    """GET /rules/{ruleId}/bindings — every group this rule is bound to."""
    kwargs = {
        "KeyConditionExpression": "pk = :pk AND begins_with(sk, :sk_prefix)",
        "ExpressionAttributeValues": {":pk": _pk(rule_id), ":sk_prefix": "GROUP#"},
        "Limit": limit,
    }
    if cursor:
        kwargs["ExclusiveStartKey"] = {"pk": _pk(rule_id), "sk": cursor}
    result = _table.query(**kwargs)
    return {
        "items": [_to_binding_view(i) for i in result.get("Items", [])],
        "next_cursor": (result.get("LastEvaluatedKey") or {}).get("sk"),
        "count": result.get("Count", 0),
    }


def list_bindings_for_group(group: str, limit: int = 20, cursor: str = None) -> dict:
    """GET /groups/{group}/bindings — every rule bound to this group, via gsi1."""
    kwargs = {
        "IndexName": GSI1_NAME,
        "KeyConditionExpression": "gsi1pk = :gsi1pk",
        "ExpressionAttributeValues": {":gsi1pk": _gsi1pk(group)},
        "Limit": limit,
    }
    if cursor:
        kwargs["ExclusiveStartKey"] = {"gsi1pk": _gsi1pk(group), "gsi1sk": cursor}
    result = _table.query(**kwargs)
    return {
        "items": [_to_binding_view(i) for i in result.get("Items", [])],
        "next_cursor": (result.get("LastEvaluatedKey") or {}).get("gsi1sk"),
        "count": result.get("Count", 0),
    }


def get_binding(rule_id: str, group: str, binding: str) -> dict:
    result = _table.get_item(Key={"pk": _pk(rule_id), "sk": _sk(group, binding)})
    item = result.get("Item")
    if not item:
        raise NotFoundError(
            f"Binding not found for rule '{rule_id}', group '{group}', binding '{binding}'.",
            details={"rule_id": rule_id, "group": group, "binding": binding},
        )
    return _to_binding_view(item)


def create_binding(rule_id: str, group: str, binding: str, payload: dict) -> dict:
    timestamp = now_iso()
    item = {
        "pk": _pk(rule_id),
        "sk": _sk(group, binding),
        "gsi1pk": _gsi1pk(group),
        "gsi1sk": _gsi1sk(rule_id, binding),
        "payload": payload,
        "created_at": timestamp,
        "updated_at": timestamp,
    }
    try:
        _table.put_item(Item=item, ConditionExpression="attribute_not_exists(pk)")
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConflictError(
                f"Binding already exists for rule '{rule_id}', group '{group}', binding '{binding}'.",
                details={"rule_id": rule_id, "group": group, "binding": binding},
            )
        raise
    return _to_binding_view(item)


def update_binding(rule_id: str, group: str, binding: str, payload: dict, expected_version) -> dict:
    # Full replace semantics for PUT: the caller's payload becomes the new
    # rule configuration for this group/binding. created_at is preserved.
    #
    # Optimistic locking: the caller must pass `expected_version`, the
    # version they last read. The conditional write only succeeds if the
    # item currently stored still has that same payload.version, so a
    # concurrent writer that already bumped the version causes this write to
    # fail with a 409 instead of silently clobbering the other change.
    existing = get_binding(rule_id, group, binding)
    item = {
        "pk": _pk(rule_id),
        "sk": _sk(group, binding),
        "gsi1pk": _gsi1pk(group),
        "gsi1sk": _gsi1sk(rule_id, binding),
        "payload": payload,
        "created_at": existing["created_at"],
        "updated_at": now_iso(),
    }
    try:
        _table.put_item(
            Item=item,
            ConditionExpression="attribute_exists(pk) AND payload.version = :expected_version",
            ExpressionAttributeValues={":expected_version": expected_version},
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise ConflictError(
                f"Binding for rule '{rule_id}', group '{group}', binding '{binding}' was "
                f"changed by someone else since you last read it (expected version "
                f"{expected_version}, found {existing['payload'].get('version')}). Refetch "
                "and retry.",
                details={
                    "rule_id": rule_id,
                    "group": group,
                    "binding": binding,
                    "expected_version": expected_version,
                    "actual_version": existing["payload"].get("version"),
                },
            )
        raise
    return _to_binding_view(item)


def list_distinct_rule_ids() -> list:
    """GET /rules — every rule ID that has at least one binding.

    There's no dedicated rule-catalog data source yet (that's separate,
    larger scope — see docs/BLUEPRINT.md §12 roadmap step 7's open half).
    This treats "rules with at least one binding in
    y62db-config-rule-catalog" as the searchable universe for now, which is
    what the UI's client-side fuzzy rule-ID search needs candidates for.
    Does a full table Scan (paginated internally) and dedupes by pk — fine
    at this table's current size, but would need a smarter approach (a
    dedicated GSI or a real rule catalog) if the table grows large.
    """
    rule_ids = set()
    kwargs = {"ProjectionExpression": "pk"}
    while True:
        result = _table.scan(**kwargs)
        for item in result.get("Items", []):
            pk = item.get("pk", "")
            if pk.startswith("RULE#"):
                rule_ids.add(pk.split("RULE#", 1)[1])
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return sorted(rule_ids)


def list_distinct_groups() -> list:
    """GET /groups — every group that has at least one binding.

    Same rationale and same caveats as `list_distinct_rule_ids` above, just
    extracting the group out of `sk` ("GROUP#<group>#BINDING#<binding>")
    instead of the rule ID out of `pk`.
    """
    groups = set()
    kwargs = {"ProjectionExpression": "sk"}
    while True:
        result = _table.scan(**kwargs)
        for item in result.get("Items", []):
            sk = item.get("sk", "")
            if sk.startswith("GROUP#"):
                groups.add(sk.split("#")[1])
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    return sorted(groups)


def delete_binding(rule_id: str, group: str, binding: str) -> None:
    try:
        _table.delete_item(
            Key={"pk": _pk(rule_id), "sk": _sk(group, binding)},
            ConditionExpression="attribute_exists(pk)",
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] == "ConditionalCheckFailedException":
            raise NotFoundError(
                f"Binding not found for rule '{rule_id}', group '{group}', binding '{binding}'.",
                details={"rule_id": rule_id, "group": group, "binding": binding},
            )
        raise
