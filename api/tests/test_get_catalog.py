import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from conftest import FakeContext, make_event


def _seed_catalog_entry(dynamodb_table, rule_id, num_params=1):
    dynamodb_table._table.put_item(
        Item={
            "pk": f"RULE#{rule_id}",
            "sk": f"PROFILE#{rule_id}",
            "entity_type": "RULE_PROFILE",
            "rule_id": rule_id,
            "source_identifier": "S3_BUCKET_VERSIONING_ENABLED",
            "description": "Checks that versioning is enabled for S3 buckets.",
            "severity": "MEDIUM",
            "scopes": ["AWS::S3::Bucket"],
            "managed_rule": True,
        }
    )
    for i in range(num_params):
        dynamodb_table._table.put_item(
            Item={
                "pk": f"RULE#{rule_id}",
                "sk": f"PARAMDEF#param{i}",
                "entity_type": "PARAMETER_DEF",
                "rule_id": rule_id,
                "parameter_name": f"param{i}",
                "data_type": "string",
                "required": i == 0,
                "default_value": "true" if i == 0 else "",
            }
        )


def test_get_catalog_returns_profile_and_parameters(dynamodb_table, monkeypatch):
    import handler
    import rules.get_catalog as rules_get_catalog

    monkeypatch.setattr(rules_get_catalog, "dynamodb", dynamodb_table)
    _seed_catalog_entry(dynamodb_table, "s3-bucket-versioning-enabled", num_params=2)

    result = handler.lambda_handler(
        make_event("GET", "/rules/{ruleId}/catalog", path_params={"ruleId": "s3-bucket-versioning-enabled"}),
        FakeContext(),
    )
    assert result["statusCode"] == 200
    body = json.loads(result["body"])
    assert body["success"] is True
    data = body["data"]
    assert data["rule_id"] == "s3-bucket-versioning-enabled"
    assert data["description"] == "Checks that versioning is enabled for S3 buckets."
    assert data["severity"] == "MEDIUM"
    assert data["scopes"] == ["AWS::S3::Bucket"]
    assert data["managed_rule"] is True
    assert data["parameters"] == [
        {"name": "param0", "data_type": "string", "required": True, "default_value": "true"},
        {"name": "param1", "data_type": "string", "required": False, "default_value": ""},
    ]


def test_get_catalog_404s_for_binding_only_rule(dynamodb_table, monkeypatch):
    """A rule that only exists as a QA test-artifact binding (no seeded
    RULE_PROFILE) has no catalog data to show -- must 404, not 200 with
    empty fields."""
    import handler
    import rules.get_catalog as rules_get_catalog

    monkeypatch.setattr(rules_get_catalog, "dynamodb", dynamodb_table)

    # A binding with no catalog entry, matching the real live-data shape
    # for the QA test-artifact rule IDs (e.g. "a2_1").
    dynamodb_table._table.put_item(
        Item={
            "pk": "RULE#a2_1",
            "sk": "GROUP#corp#BINDING#default",
            "gsi1pk": "GROUP#corp",
            "gsi1sk": "RULE#a2_1#BINDING#default",
            "payload": {"status": "ACTIVE", "version": 1},
        }
    )

    result = handler.lambda_handler(
        make_event("GET", "/rules/{ruleId}/catalog", path_params={"ruleId": "a2_1"}),
        FakeContext(),
    )
    assert result["statusCode"] == 404
    body = json.loads(result["body"])
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"
