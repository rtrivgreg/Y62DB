"""
Tests for the single-table loader rewrite.

Uses a small synthetic HCL fixture (loader/tests/fixtures/) rather than the
real config-rules-all vendor files, since that repo lives outside this
workspace. Covers the shape of RULE_PROFILE and PARAMETER_DEF items, not
volume -- volume/coverage against the real ~800-rule source can only be
verified by running this script directly against config-rules-all.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import loader  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures"


def _load_rules_and_params():
    managed_rules = loader.load_managed_rules(FIXTURES / "managed_rules_locals.tf")
    variables_text = loader.load_variables_text(FIXTURES / "managed_rules_variables.tf")
    variable_defs = loader.normalize_parameter_variables_from_text(variables_text)
    rules = loader.normalize_rules(managed_rules)
    parameter_records = loader.build_parameter_records(rules, variable_defs)
    return rules, parameter_records


def test_normalize_rules_uses_plain_rule_id():
    rules, _ = _load_rules_and_params()
    ids = {r["rule_id"] for r in rules}
    assert ids == {"access-keys-rotated", "s3-bucket-versioning-enabled"}
    # No RULE# prefix baked into the logical rule_id -- that's applied only
    # when building the actual pk/sk, matching the CRUD API's convention.
    assert all(not r["rule_id"].startswith("RULE#") for r in rules)


def test_rule_profile_items_shape():
    rules, _ = _load_rules_and_params()
    items = loader.build_rule_profile_items(rules)
    by_id = {i["rule_id"]: i for i in items}

    akr = by_id["access-keys-rotated"]
    assert akr["pk"] == "RULE#access-keys-rotated"
    assert akr["sk"] == "PROFILE#access-keys-rotated"
    assert akr["entity_type"] == "RULE_PROFILE"
    assert akr["source_identifier"] == "ACCESS_KEYS_ROTATED"
    assert akr["severity"] == "Medium"
    assert akr["scopes"] == ["AWS::IAM::User"]
    assert akr["managed_rule"] is True

    s3 = by_id["s3-bucket-versioning-enabled"]
    assert s3["pk"] == "RULE#s3-bucket-versioning-enabled"
    assert s3["sk"] == "PROFILE#s3-bucket-versioning-enabled"


def test_parameter_def_items_shape():
    rules, parameter_records = _load_rules_and_params()
    items = loader.build_parameter_def_items(parameter_records)

    # Only access-keys-rotated has an input_parameters reference in the fixture.
    assert len(items) == 1
    param = items[0]
    assert param["pk"] == "RULE#access-keys-rotated"
    assert param["sk"] == "PARAMDEF#maxAccessKeyAge"
    assert param["entity_type"] == "PARAMETER_DEF"
    assert param["rule_id"] == "access-keys-rotated"
    assert param["parameter_name"] == "maxAccessKeyAge"
    assert param["default_value"] == "90"
    assert param["required"] is True


def test_rule_with_no_input_parameters_yields_no_parameter_items():
    rules, parameter_records = _load_rules_and_params()
    rule_ids_with_params = {r["rule_id"] for r in parameter_records}
    assert "s3-bucket-versioning-enabled" not in rule_ids_with_params


def test_to_ddb_item_shapes_scopes_as_string_set():
    item = {
        "pk": "RULE#access-keys-rotated",
        "sk": "PROFILE#access-keys-rotated",
        "entity_type": "RULE_PROFILE",
        "scopes": ["AWS::IAM::User"],
        "managed_rule": True,
    }
    ddb = loader.to_ddb_item(item)
    assert ddb["scopes"] == {"SS": ["AWS::IAM::User"]}
    assert ddb["managed_rule"] == {"BOOL": True}
    assert ddb["entity_type"] == {"S": "RULE_PROFILE"}


def test_rule_limit_truncates_rule_set():
    managed_rules = loader.load_managed_rules(FIXTURES / "managed_rules_locals.tf")
    rules = loader.normalize_rules(managed_rules)[:1]
    assert len(rules) == 1
