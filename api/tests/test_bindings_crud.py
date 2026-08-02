import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from conftest import FakeContext, make_event


def _patch_dynamodb(monkeypatch, dynamodb_table):
    import bindings.create as create
    import bindings.delete as delete
    import bindings.get as get
    import bindings.list_by_group as list_by_group
    import bindings.list_by_rule as list_by_rule
    import bindings.update as update

    for module in (create, get, update, delete, list_by_rule, list_by_group):
        monkeypatch.setattr(module, "dynamodb", dynamodb_table)
    return create, get, update, delete, list_by_rule, list_by_group


def test_full_crud_lifecycle(dynamodb_table, monkeypatch):
    _patch_dynamodb(monkeypatch, dynamodb_table)
    import handler

    ctx = FakeContext()
    rule_id = "access-keys-rotated"
    body = json.dumps({"group": "corp", "binding": "default", "payload": {"status": "ACTIVE", "version": 1, "maxAccessKeyAge": 60}})

    # CREATE
    create_result = handler.lambda_handler(
        make_event("POST", "/rules/{ruleId}/bindings", path_params={"ruleId": rule_id}, body=body), ctx
    )
    assert create_result["statusCode"] == 201
    created = json.loads(create_result["body"])["data"]
    assert created["rule_id"] == rule_id
    assert created["group"] == "corp"
    assert created["binding"] == "default"
    assert created["payload"]["maxAccessKeyAge"] == 60

    # Duplicate CREATE -> 409
    dup_result = handler.lambda_handler(
        make_event("POST", "/rules/{ruleId}/bindings", path_params={"ruleId": rule_id}, body=body), ctx
    )
    assert dup_result["statusCode"] == 409

    # READ
    get_result = handler.lambda_handler(
        make_event(
            "GET",
            "/rules/{ruleId}/bindings/{group}/{binding}",
            path_params={"ruleId": rule_id, "group": "corp", "binding": "default"},
        ),
        ctx,
    )
    assert get_result["statusCode"] == 200
    assert json.loads(get_result["body"])["data"]["payload"]["status"] == "ACTIVE"

    # LIST by rule
    list_rule_result = handler.lambda_handler(
        make_event("GET", "/rules/{ruleId}/bindings", path_params={"ruleId": rule_id}), ctx
    )
    assert list_rule_result["statusCode"] == 200
    assert len(json.loads(list_rule_result["body"])["data"]) == 1

    # LIST by group (via gsi1)
    list_group_result = handler.lambda_handler(
        make_event("GET", "/groups/{group}/bindings", path_params={"group": "corp"}), ctx
    )
    assert list_group_result["statusCode"] == 200
    assert len(json.loads(list_group_result["body"])["data"]) == 1

    # UPDATE with a stale expected_version -> 409, no lost update
    stale_update_body = json.dumps(
        {"payload": {"status": "INACTIVE", "version": 2, "maxAccessKeyAge": 90}, "expected_version": 0}
    )
    stale_update_result = handler.lambda_handler(
        make_event(
            "PUT",
            "/rules/{ruleId}/bindings/{group}/{binding}",
            path_params={"ruleId": rule_id, "group": "corp", "binding": "default"},
            body=stale_update_body,
        ),
        ctx,
    )
    assert stale_update_result["statusCode"] == 409
    still_original = handler.lambda_handler(
        make_event(
            "GET",
            "/rules/{ruleId}/bindings/{group}/{binding}",
            path_params={"ruleId": rule_id, "group": "corp", "binding": "default"},
        ),
        ctx,
    )
    assert json.loads(still_original["body"])["data"]["payload"]["status"] == "ACTIVE"

    # UPDATE (full replace of payload) with the correct expected_version
    update_body = json.dumps(
        {"payload": {"status": "INACTIVE", "version": 2, "maxAccessKeyAge": 90}, "expected_version": 1}
    )
    update_result = handler.lambda_handler(
        make_event(
            "PUT",
            "/rules/{ruleId}/bindings/{group}/{binding}",
            path_params={"ruleId": rule_id, "group": "corp", "binding": "default"},
            body=update_body,
        ),
        ctx,
    )
    assert update_result["statusCode"] == 200
    updated = json.loads(update_result["body"])["data"]
    assert updated["payload"]["status"] == "INACTIVE"
    assert updated["payload"]["maxAccessKeyAge"] == 90

    # DELETE
    delete_result = handler.lambda_handler(
        make_event(
            "DELETE",
            "/rules/{ruleId}/bindings/{group}/{binding}",
            path_params={"ruleId": rule_id, "group": "corp", "binding": "default"},
        ),
        ctx,
    )
    assert delete_result["statusCode"] == 204
    assert delete_result["body"] == ""

    # GET after DELETE -> 404
    get_after_delete = handler.lambda_handler(
        make_event(
            "GET",
            "/rules/{ruleId}/bindings/{group}/{binding}",
            path_params={"ruleId": rule_id, "group": "corp", "binding": "default"},
        ),
        ctx,
    )
    assert get_after_delete["statusCode"] == 404
    assert json.loads(get_after_delete["body"])["error"]["code"] == "not_found"


def test_create_binding_defaults_binding_name(dynamodb_table, monkeypatch):
    _patch_dynamodb(monkeypatch, dynamodb_table)
    import handler

    body = json.dumps({"group": "corp", "payload": {"status": "ACTIVE", "version": 1}})
    result = handler.lambda_handler(
        make_event("POST", "/rules/{ruleId}/bindings", path_params={"ruleId": "s3-bucket-public-read-prohibited"}, body=body),
        FakeContext(),
    )
    assert result["statusCode"] == 201
    assert json.loads(result["body"])["data"]["binding"] == "default"


def test_create_binding_invalid_payload_status_returns_400(dynamodb_table, monkeypatch):
    _patch_dynamodb(monkeypatch, dynamodb_table)
    import handler

    body = json.dumps({"group": "corp", "payload": {"status": "BOGUS", "version": 1}})
    result = handler.lambda_handler(
        make_event("POST", "/rules/{ruleId}/bindings", path_params={"ruleId": "access-keys-rotated"}, body=body),
        FakeContext(),
    )
    assert result["statusCode"] == 400
    assert json.loads(result["body"])["error"]["code"] == "validation_error"


def test_unknown_route_returns_404(dynamodb_table, monkeypatch):
    import handler

    result = handler.lambda_handler(make_event("PATCH", "/rules/{ruleId}/bindings"), FakeContext())
    assert result["statusCode"] == 404
    assert json.loads(result["body"])["error"]["code"] == "route_not_found"
