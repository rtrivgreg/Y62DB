import os
import sys

import boto3
import pytest
from moto import mock_aws

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

TABLE_NAME = "y62db-config-rule-catalog-test"
GSI1_NAME = "gsi1"
os.environ["CONFIG_RULE_CATALOG_TABLE"] = TABLE_NAME
os.environ["CONFIG_RULE_CATALOG_GSI1"] = GSI1_NAME
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")


@pytest.fixture
def dynamodb_table():
    with mock_aws():
        client = boto3.resource("dynamodb", region_name="us-east-1")
        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
                {"AttributeName": "gsi1pk", "AttributeType": "S"},
                {"AttributeName": "gsi1sk", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": GSI1_NAME,
                    "KeySchema": [
                        {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                        {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        # common.dynamodb module-level `_table` is bound at import time, so
        # reload it here to pick up the mocked resource for this test.
        import importlib

        import common.dynamodb as dynamodb_module

        importlib.reload(dynamodb_module)
        yield dynamodb_module


def make_event(method: str, resource: str, path_params: dict = None, body=None, query=None):
    return {
        "httpMethod": method,
        "resource": resource,
        "pathParameters": path_params,
        "queryStringParameters": query,
        "body": body,
    }


class FakeContext:
    aws_request_id = "test-request-id"
