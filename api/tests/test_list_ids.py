import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from conftest import FakeContext, make_event


def _create_binding(monkeypatch, dynamodb_table, rule_id, group, binding="default"):
    import bindings.create as create

    monkeypatch.setattr(create, "dynamodb", dynamodb_table)
    body = json.dumps({"group": group, "binding": binding, "payload": {"status": "ACTIVE", "version": 1}})
    import handler

    result = handler.lambda_handler(
        make_event("POST", "/rules/{ruleId}/bindings", path_params={"ruleId": rule_id}, body=body),
        FakeContext(),
    )
    assert result["statusCode"] == 201, result["body"]


def test_list_rule_ids_returns_distinct_sorted_ids(dynamodb_table, monkeypatch):
    import handler
    import rules.list_ids as rules_list_ids

    monkeypatch.setattr(rules_list_ids, "dynamodb", dynamodb_table)

    # Two bindings under the same rule (different groups) + one under a
    # second rule -- the distinct-rule-id list should collapse the first
    # rule to a single entry and be alphabetically sorted.
    _create_binding(monkeypatch, dynamodb_table, "access-keys-rotated", "corp")
    _create_binding(monkeypatch, dynamodb_table, "access-keys-rotated", "eng")
    _create_binding(monkeypatch, dynamodb_table, "access-keys-rotated2", "corp")

    result = handler.lambda_handler(make_event("GET", "/rules"), FakeContext())
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["success"] is True
    assert body["data"] == ["access-keys-rotated", "access-keys-rotated2"]
    assert body["meta"]["count"] == 2


def test_list_groups_returns_distinct_sorted_groups(dynamodb_table, monkeypatch):
    import handler
    import groups.list_ids as groups_list_ids

    monkeypatch.setattr(groups_list_ids, "dynamodb", dynamodb_table)

    _create_binding(monkeypatch, dynamodb_table, "access-keys-rotated", "corp")
    _create_binding(monkeypatch, dynamodb_table, "access-keys-rotated2", "corp")
    _create_binding(monkeypatch, dynamodb_table, "access-keys-rotated2", "eng")

    result = handler.lambda_handler(make_event("GET", "/groups"), FakeContext())
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["success"] is True
    assert body["data"] == ["corp", "eng"]
    assert body["meta"]["count"] == 2


def test_list_rule_ids_empty_table_returns_empty_list(dynamodb_table, monkeypatch):
    import handler
    import rules.list_ids as rules_list_ids

    monkeypatch.setattr(rules_list_ids, "dynamodb", dynamodb_table)

    result = handler.lambda_handler(make_event("GET", "/rules"), FakeContext())
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["data"] == []
    assert body["meta"]["count"] == 0


def test_list_rule_ids_excludes_catalog_only_rules(dynamodb_table, monkeypatch):
    """Regression test for docs/BLUEPRINT.md §12.10.

    The §11 loader seeds `RULE_PROFILE` (sk="PROFILE#<ruleId>") and
    `PARAMETER_DEF` (sk="PARAMDEF#<parameterName>") items into this same
    table, sharing the "RULE#<ruleId>" pk prefix with real `RULE_BINDING`
    items. `GET /rules` must only ever surface rules with an actual
    binding, never every rule in the catalog.
    """
    import handler
    import rules.list_ids as rules_list_ids

    monkeypatch.setattr(rules_list_ids, "dynamodb", dynamodb_table)

    # A real binding for one rule.
    _create_binding(monkeypatch, dynamodb_table, "s3-bucket-versioning-enabled", "corp")

    # Catalog-only items for OTHER rules -- as the real loader writes them
    # -- with no binding at all. These must never show up in GET /rules.
    dynamodb_table._table.put_item(
        Item={
            "pk": "RULE#s3-bucket-public-read-prohibited",
            "sk": "PROFILE#s3-bucket-public-read-prohibited",
            "entity_type": "RULE_PROFILE",
            "rule_id": "s3-bucket-public-read-prohibited",
        }
    )
    dynamodb_table._table.put_item(
        Item={
            "pk": "RULE#s3-bucket-versioning-enabled",
            "sk": "PARAMDEF#someParam",
            "entity_type": "PARAMETER_DEF",
            "rule_id": "s3-bucket-versioning-enabled",
            "parameter_name": "someParam",
        }
    )

    result = handler.lambda_handler(make_event("GET", "/rules"), FakeContext())
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["success"] is True
    # Only the rule with a real binding shows up -- the RULE_PROFILE-only
    # rule (s3-bucket-public-read-prohibited) and the PARAMETER_DEF item
    # (which shares a pk with the bound rule but isn't itself a binding)
    # must not leak into the candidate list.
    assert body["data"] == ["s3-bucket-versioning-enabled"]
    assert body["meta"]["count"] == 1
