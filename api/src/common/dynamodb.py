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


def list_all_rules_with_binding_status() -> list:
    """GET /rules — every rule the UI needs to know about, catalog + bound.

    See docs/BLUEPRINT.md §12.11. Replaces the old `list_distinct_rule_ids`
    (bindings-only) as the backing function for `GET /rules`: this endpoint
    now powers both the rule-ID search box (which must be able to find
    catalog-only rules too,
    so users can create a first binding for them) and the Create Binding
    rule picker. Returns the *union* of every rule ID that has a
    `RULE_PROFILE` catalog item (sk="PROFILE#<ruleId>") and every rule ID
    that has at least one real `RULE_BINDING` item (sk begins with
    "GROUP#" and contains "#BINDING#"), each tagged with whether it
    currently has a binding:

        [{"rule_id": "...", "has_binding": bool}, ...]

    sorted by rule_id. A rule with both a catalog entry and a binding
    appears exactly once, with has_binding=True.

    Does a full table Scan (paginated internally), same approach and same
    scaling caveat as before.
    """
    catalog_ids = set()
    bound_ids = set()
    kwargs = {"ProjectionExpression": "pk, sk"}
    while True:
        result = _table.scan(**kwargs)
        for item in result.get("Items", []):
            pk = item.get("pk", "")
            sk = item.get("sk", "")
            if not pk.startswith("RULE#"):
                continue
            rule_id = pk.split("RULE#", 1)[1]
            if sk.startswith("PROFILE#"):
                catalog_ids.add(rule_id)
            elif sk.startswith("GROUP#") and "#BINDING#" in sk:
                bound_ids.add(rule_id)
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs["ExclusiveStartKey"] = last_key
    all_ids = catalog_ids | bound_ids
    return [{"rule_id": rule_id, "has_binding": rule_id in bound_ids} for rule_id in sorted(all_ids)]


def get_rule_catalog(rule_id: str) -> dict:
    """GET /rules/{ruleId}/catalog — full catalog entry for one rule.

    Reads the `RULE_PROFILE` item (pk="RULE#<ruleId>", sk="PROFILE#<ruleId>")
    seeded by ``loader/loader.py``, plus every `PARAMETER_DEF` item under the
    same pk (sk begins_with "PARAMDEF#"). Rules that only exist because
    they have a binding but were never in the seeded catalog (e.g. the QA
    test artifacts like "a2_1") have no RULE_PROFILE item -- 404s here,
    since there's no catalog data to return.
    """
    result = _table.get_item(Key={"pk": _pk(rule_id), "sk": f"PROFILE#{rule_id}"})
    profile = result.get("Item")
    if not profile:
        raise NotFoundError(
            f"No catalog entry found for rule '{rule_id}'.",
            details={"rule_id": rule_id},
        )

    param_result = _table.query(
        KeyConditionExpression="pk = :pk AND begins_with(sk, :sk_prefix)",
        ExpressionAttributeValues={":pk": _pk(rule_id), ":sk_prefix": "PARAMDEF#"},
    )
    parameters = [
        {
            "name": p.get("parameter_name"),
            "data_type": p.get("data_type"),
            "required": p.get("required", False),
            "default_value": p.get("default_value"),
        }
        for p in param_result.get("Items", [])
    ]
    parameters.sort(key=lambda p: p["name"] or "")

    return {
        "rule_id": rule_id,
        "source_identifier": profile.get("source_identifier", ""),
        "description": profile.get("description", ""),
        "severity": profile.get("severity", ""),
        "scopes": sorted(profile.get("scopes", []) or []),
        "managed_rule": profile.get("managed_rule", False),
        "parameters": parameters,
    }


def list_distinct_groups() -> list:
    """GET /groups — every group that has at least one binding.

    Same rationale and same caveats as `list_all_rules_with_binding_status`
    above, just extracting the group out of `sk`
    ("GROUP#<group>#BINDING#<binding>") instead of the rule ID out of `pk`.
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
