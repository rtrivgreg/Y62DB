import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from common import response


def test_success_envelope_shape():
    result = response.success(200, data={"id": "1"})
    body = json.loads(result["body"])
    assert result["statusCode"] == 200
    assert body["success"] is True
    assert body["data"] == {"id": "1"}
    assert body["error"] is None
    assert "request_id" in body["meta"]


def test_success_204_has_no_body():
    result = response.success(204, data=None)
    assert result["statusCode"] == 204
    assert result["body"] == ""


def test_error_envelope_shape():
    result = response.error(404, "not_found", "Item not found.")
    body = json.loads(result["body"])
    assert result["statusCode"] == 404
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"
    assert body["data"] is None
