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
    # second rule -- the merged rule list should collapse the first rule
    # to a single entry, be alphabetically sorted, and tag both as bound
    # (has_binding=True) since neither has a seeded catalog entry.
    _create_binding(monkeypatch, dynamodb_table, "access-keys-rotated", "corp")
    _create_binding(monkeypatch, dynamodb_table, "access-keys-rotated", "eng")
    _create_binding(monkeypatch, dynamodb_table, "access-keys-rotated2", "corp")

    result = handler.lambda_handler(make_event("GET", "/rules"), FakeContext())
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["success"] is True
    assert body["data"] == [
        {"rule_id": "access-keys-rotated", "has_binding": True},
        {"rule_id": "access-keys-rotated2", "has_binding": True},
    ]
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


def test_list_rule_ids_merges_catalog_and_bindings(dynamodb_table, monkeypatch):
    """Regression test for docs/BLUEPRINT.md §12.10 and §12.11.

    The §11 loader seeds `RULE_PROFILE` (sk="PROFILE#<ruleId>") and
    `PARAMETER_DEF` (sk="PARAMDEF#<parameterName>") items into this same
    table, sharing the "RULE#<ruleId>" pk prefix with real `RULE_BINDING`
    items. As of §12.11, `GET /rules` is the merged catalog+bindings view:
    every rule with a binding, every rule with only a catalog entry, and a
    `has_binding` flag distinguishing the two -- plus a `PARAMETER_DEF`
    item under a bound rule's pk must never be mistaken for a distinct
    third rule.
    """
    import handler
    import rules.list_ids as rules_list_ids

    monkeypatch.setattr(rules_list_ids, "dynamodb", dynamodb_table)

    # A real binding for one rule that ALSO has no catalog entry of its own
    # here (has_binding=True, still appears once).
    _create_binding(monkeypatch, dynamodb_table, "s3-bucket-versioning-enabled", "corp")

    # A catalog-only item for another rule -- as the real loader writes it
    # -- with no binding at all (has_binding=False).
    dynamodb_table._table.put_item(
        Item={
            "pk": "RULE#s3-bucket-public-read-prohibited",
            "sk": "PROFILE#s3-bucket-public-read-prohibited",
            "entity_type": "RULE_PROFILE",
            "rule_id": "s3-bucket-public-read-prohibited",
        }
    )
    # A PARAMETER_DEF item under the bound rule's pk -- shares a pk with a
    # bound rule but must not be counted as its own rule entry.
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
    # Both rules show up exactly once each, correctly tagged -- the
    # PARAMETER_DEF item does not leak in as a third entry.
    assert body["data"] == [
        {"rule_id": "s3-bucket-public-read-prohibited", "has_binding": False},
        {"rule_id": "s3-bucket-versioning-enabled", "has_binding": True},
    ]
    assert body["meta"]["count"] == 2
