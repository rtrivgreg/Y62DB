import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from common.exceptions import ValidationError
from common.validation import Field, Schema, validate


@validate(Schema(path_params=["id"], require_body=True, body_fields=[Field(name="name", required=True)]))
def sample_handler(event, context, path_params=None, body=None):
    return {"path_params": path_params, "body": body}


def _event(path_params=None, body=None):
    return {"pathParameters": path_params, "body": body}


def test_missing_path_param_raises():
    with pytest.raises(ValidationError):
        sample_handler(_event(path_params=None, body=json.dumps({"name": "x"})), None)


def test_missing_body_raises():
    with pytest.raises(ValidationError):
        sample_handler(_event(path_params={"id": "1"}, body=None), None)


def test_invalid_json_body_raises():
    with pytest.raises(ValidationError):
        sample_handler(_event(path_params={"id": "1"}, body="not-json"), None)


def test_missing_required_field_raises():
    with pytest.raises(ValidationError):
        sample_handler(_event(path_params={"id": "1"}, body=json.dumps({})), None)


def test_valid_request_passes_through():
    result = sample_handler(_event(path_params={"id": "1"}, body=json.dumps({"name": "widget"})), None)
    assert result["path_params"] == {"id": "1"}
    assert result["body"] == {"name": "widget"}
