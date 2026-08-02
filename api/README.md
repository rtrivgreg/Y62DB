# Y62DB Rule-Catalog CRUD API

A Python AWS Lambda + API Gateway CRUD API for the **`y62db-config-rule-catalog`**
DynamoDB table (`us-east-1`) — the table you've already created and seeded
as part of the Y62DB project. This is not a standalone/generic template: it's
built against your actual single-table design and is meant to be folded into
your existing Y62DB Terraform Cloud workspace.

## Your table's schema (as-is, not created by this project)

Single-table design, one item = one **binding** of an AWS Config managed
rule's configuration to a group:

| Attribute | Example                                      | Meaning                                  |
|-----------|-----------------------------------------------|-------------------------------------------|
| `pk`      | `RULE#access-keys-rotated`                    | Partition key — the Config rule           |
| `sk`      | `GROUP#corp#BINDING#default`                  | Sort key — group + binding name           |
| `gsi1pk`  | `GROUP#corp`                                  | GSI (`gsi1`) partition key                |
| `gsi1sk`  | `RULE#access-keys-rotated#BINDING#default`    | GSI sort key                              |
| `payload` | `{ "status": "ACTIVE", "version": 1, "maxAccessKeyAge": 60 }` | Rule-specific configuration |

This lets you query two ways: "every group a rule is bound to" (base table,
`pk`) and "every rule bound to a group" (`gsi1`, `gsi1pk`) — which is exactly
what the two list endpoints below use.

## Architecture

```
API Gateway (REST API, AWS_PROXY) ──▶ Lambda (single function, internal router) ──▶ y62db-config-rule-catalog
```

One Lambda function fronts every route. `src/handler.py` dispatches on
`(httpMethod, resource)` to a resource module in `src/bindings/`, wrapped by
validation middleware (`src/common/validation.py`) and centralized error
handling that always returns the standardized envelope (`src/common/response.py`).

```
aws-lambda-crud-api/
├── src/
│   ├── handler.py               # Lambda entry point + route table
│   ├── common/
│   │   ├── response.py          # Standardized success/error envelope
│   │   ├── validation.py        # Declarative request validation middleware
│   │   ├── dynamodb.py          # Access layer for y62db-config-rule-catalog
│   │   └── exceptions.py        # ApiError hierarchy -> HTTP status codes
│   └── bindings/
│       ├── list_by_rule.py      # GET    /rules/{ruleId}/bindings
│       ├── create.py            # POST   /rules/{ruleId}/bindings
│       ├── get.py               # GET    /rules/{ruleId}/bindings/{group}/{binding}
│       ├── update.py            # PUT    /rules/{ruleId}/bindings/{group}/{binding}
│       ├── delete.py            # DELETE /rules/{ruleId}/bindings/{group}/{binding}
│       └── list_by_group.py     # GET    /groups/{group}/bindings
├── tests/                       # pytest + moto (mocked DynamoDB, same key schema)
├── terraform/                   # IAM, Lambda, API Gateway (table referenced via data source)
├── requirements.txt
└── requirements-dev.txt
```

## API contract

### Design principles

- **Plural, noun-based resource paths**, nested to reflect the real
  relationship in your data: a binding belongs to a rule (`/rules/{ruleId}/bindings`)
  and can also be looked up by group (`/groups/{group}/bindings`).
- **No verbs in the path.** The HTTP method is the verb.
- **HTTP verbs map onto DynamoDB operations:**

  | HTTP method | Path                                         | DynamoDB operation                                  | Semantics                          |
  |-------------|-----------------------------------------------|------------------------------------------------------|--------------------------------------|
  | `GET`       | `/rules/{ruleId}/bindings`                    | `Query` on base table (`pk`, `sk begins_with`)        | List every group a rule is bound to |
  | `POST`      | `/rules/{ruleId}/bindings`                    | `PutItem` (`attribute_not_exists(pk)`)                | Create a binding                    |
  | `GET`       | `/rules/{ruleId}/bindings/{group}/{binding}`  | `GetItem`                                             | Retrieve one binding                |
  | `PUT`       | `/rules/{ruleId}/bindings/{group}/{binding}`  | `PutItem` (`attribute_exists(pk) AND payload.version = :expected_version`, full replace) | Replace a binding's payload |
  | `DELETE`    | `/rules/{ruleId}/bindings/{group}/{binding}`  | `DeleteItem` (`attribute_exists(pk)`)                 | Remove a binding                     |
  | `GET`       | `/groups/{group}/bindings`                    | `Query` on `gsi1` (`gsi1pk`)                          | List every rule bound to a group    |

  `PUT` performs a full replace of `payload` (standard REST semantics) —
  `rule_id`, `group`, `binding`, and `created_at` are preserved from the
  existing record. Updates use **optimistic locking on the payload's
  `version` field**, per the catalog's suggested access patterns: the
  request must include `expected_version` (the version the caller last
  read), and the write is rejected with `409` if the stored version has
  since moved on — preventing lost updates from concurrent editors.

- **Status codes:** `200` (read/update), `201` (created), `204` (deleted, no
  body), `400` (validation), `404` (not found / unknown route), `409`
  (conflict — binding already exists, or a stale `expected_version` on
  update), `500` (unhandled).

### Standardized response envelope

Every response — success or error — has the same shape:

**Success**
```json
{
  "success": true,
  "data": {
    "rule_id": "access-keys-rotated",
    "group": "corp",
    "binding": "default",
    "payload": { "status": "ACTIVE", "version": 1, "maxAccessKeyAge": 60 },
    "created_at": "2026-08-01T23:00:00+00:00",
    "updated_at": "2026-08-01T23:00:00+00:00"
  },
  "error": null,
  "meta": { "request_id": "c2b4...", "timestamp": "2026-08-01T23:00:00+00:00" }
}
```

**Error**
```json
{
  "success": false,
  "data": null,
  "error": {
    "code": "validation_error",
    "message": "Payload failed validation.",
    "details": { "fields": ["'payload.status' must be one of ['ACTIVE', 'INACTIVE']."] }
  },
  "meta": { "request_id": "c2b4...", "timestamp": "2026-08-01T23:00:00+00:00" }
}
```

The internal `pk`/`sk`/`gsi1pk`/`gsi1sk` attributes are never exposed to API
consumers — every response translates them into `rule_id` / `group` /
`binding` fields. List endpoints additionally set `meta.count` and
`meta.next_cursor` for pagination (`?limit=...&cursor=...`). `DELETE` returns
`204` with an empty body per RFC 7231.

### Endpoints

#### `GET /rules/{ruleId}/bindings`
List every group `ruleId` is bound to.
```
GET /rules/access-keys-rotated/bindings
200 OK -> data: [ { "rule_id": "access-keys-rotated", "group": "corp", "binding": "default", "payload": {...}, ... } ]
```

#### `POST /rules/{ruleId}/bindings`
Create a binding.

Request body:
```json
{ "group": "corp", "binding": "default", "payload": { "status": "ACTIVE", "version": 1, "maxAccessKeyAge": 60 } }
```
| Field             | Type   | Required | Notes                                              |
|--------------------|--------|----------|------------------------------------------------------|
| `group`            | string | yes      | 1–100 characters                                      |
| `binding`          | string | no       | defaults to `"default"` if omitted                    |
| `payload`          | object | yes      | rule-specific config; open-ended                      |
| `payload.status`   | string | yes      | one of `ACTIVE`, `INACTIVE`                           |
| `payload.version`  | number | yes      | integer or float                                       |

Any other keys inside `payload` (e.g. `maxAccessKeyAge`) are rule-specific
and passed through as-is — this project doesn't hardcode per-rule schemas.

`201 Created` on success, `409 Conflict` if that exact rule+group+binding
already exists.

#### `GET /rules/{ruleId}/bindings/{group}/{binding}`
Retrieve one binding. `404 Not Found` if it doesn't exist.

#### `PUT /rules/{ruleId}/bindings/{group}/{binding}`
Full replace of `payload` (same `payload` schema as `POST`), guarded by
optimistic locking.

Request body:
```json
{ "payload": { "status": "INACTIVE", "version": 2, "maxAccessKeyAge": 90 }, "expected_version": 1 }
```
| Field               | Type   | Required | Notes                                                        |
|----------------------|--------|----------|----------------------------------------------------------------|
| `payload`            | object | yes      | same schema as `POST`'s `payload`                               |
| `expected_version`   | number | yes      | the `payload.version` you last read for this binding            |

`404 Not Found` if the binding doesn't exist yet — use `POST` to create it
first. `409 Conflict` if `expected_version` doesn't match what's currently
stored (someone else updated it since you read it) — refetch with `GET` and
retry with the new version.

#### `DELETE /rules/{ruleId}/bindings/{group}/{binding}`
Remove a binding. `204 No Content` on success, `404 Not Found` otherwise.

#### `GET /groups/{group}/bindings`
List every rule bound to `group`, via `gsi1`.
```
GET /groups/corp/bindings
200 OK -> data: [ { "rule_id": "access-keys-rotated", "group": "corp", "binding": "default", "payload": {...}, ... } ]
```

#### `GET /rules`
List every distinct rule ID that has at least one binding (full table scan
+ dedupe on `pk`, sorted alphabetically). There's no separate rule-catalog
data source yet, so this treats "rules with bindings" as the full universe.
Used by the UI to power client-side fuzzy rule-ID search (fetch once,
fuzzy-match locally, then fan out `GET /rules/{ruleId}/bindings` per match)
rather than as a general-purpose catalog browser.
```
GET /rules
200 OK -> data: ["access-keys-rotated", "access-keys-rotated2", ...], meta.count: 2
```

#### `GET /groups`
Same idea as `GET /rules`, for the group dimension (dedupe on `sk`'s group
segment). Powers fuzzy search in "By group" mode.
```
GET /groups
200 OK -> data: ["corp", "eng", ...], meta.count: 2
```

### Error codes

| `error.code`          | HTTP status | Meaning                                        |
|------------------------|-------------|--------------------------------------------------|
| `validation_error`     | 400         | Missing/invalid path params, body, or payload fields |
| `not_found`            | 404         | Binding does not exist                          |
| `route_not_found`      | 404         | No route matches the method + path              |
| `conflict`             | 409         | Binding already exists for that rule+group+binding |
| `internal_error`       | 500         | Unhandled exception                              |

## Local development

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
pytest tests/ -v
```

Tests use [`moto`](https://github.com/getmoto/moto) to spin up a table with
the same `pk`/`sk`/`gsi1` schema — no AWS account or network access needed.

## Deployment — merged into the Y62DB root Terraform Cloud workspace

This Lambda source lives in `api/src/`, but the Terraform that provisions it
is **not** in this folder — it's merged directly into the Y62DB repo root
(`crud_api_variables.tf`, `crud_api_dynamodb.tf`, `crud_api_iam.tf`,
`crud_api_lambda.tf`, `crud_api_gateway.tf`, `crud_api_outputs.tf`), which is
the module already wired to the Y62DB Terraform Cloud workspace
(`cloud { organization = "RSHL2136", workspaces { name = "Y62DB" } }` in
`terraform.tf`).

**Important:** `crud_api_dynamodb.tf` does **not** create the DynamoDB table
— it looks it up with `data "aws_dynamodb_table"` so it never conflicts with
however `y62db-config-rule-catalog` is actually managed. Note that the Y62DB
repo root's own `dynamodb.tf`/`locals.tf`/`outputs.tf` manage a *separate*,
legacy pair of tables (`config_rules`, `config_rule_parameters`) — this CRUD
layer does not touch those, and this workspace does not currently own the
real `y62db-config-rule-catalog` table's state either way (see
`terraform/dynamodb.tf` for that table's own definition, which has no
backend/cloud block of its own).

```bash
# from the Y62DB repo root
terraform init
terraform plan   # verify: only Lambda/IAM/API Gateway/CloudWatch additions,
                  # zero changes to config_rules/config_rule_parameters
terraform apply
```

Provisions (all new resources, additive only):

- `data "aws_dynamodb_table"` — read-only reference to `y62db-config-rule-catalog`
- `aws_iam_role` + least-privilege `aws_iam_role_policy` scoped to that table's ARN and its `gsi1-group-bindings` index ARN (`GetItem`, `PutItem`, `DeleteItem`, `Query` only)
- `aws_lambda_function` — zips `api/src/`, `handler.lambda_handler` entry point, table name passed via `CONFIG_RULE_CATALOG_TABLE` env var
- `aws_api_gateway_rest_api` with the `/rules/{ruleId}/bindings[...]` and `/groups/{group}/bindings` resource tree above, `AWS_PROXY` to the same Lambda, plus `OPTIONS` methods for CORS
- `aws_api_gateway_stage` named after `var.environment`

### Variables (defined in `crud_api_variables.tf` at the repo root)

| Variable               | Default                     | Description                                       |
|-------------------------|------------------------------|-----------------------------------------------------|
| `crud_api_name`         | `y62db-rule-catalog-api`     | Prefix for all CRUD API resource names              |
| `environment`           | `dev`                        | Shared with the rest of the root module — API Gateway stage name / resource suffix |
| `aws_region`            | `us-east-1`                  | Shared with the rest of the root module — must match the existing table's region |
| `dynamodb_table_name`   | `y62db-config-rule-catalog`  | Name of the existing table (not created here)      |
| `dynamodb_gsi1_name`    | `gsi1-group-bindings`        | Name of the existing GSI (confirmed from the original table-creation Terraform) |
| `lambda_runtime`        | `python3.12`                 | Lambda runtime                                       |
| `lambda_timeout`        | `10`                         | Lambda timeout, seconds                              |
| `lambda_memory_size`    | `256`                        | Lambda memory, MB                                    |
| `log_retention_days`    | `14`                         | CloudWatch Logs retention                            |
| `tags`                  | `{}`                         | Extra tags applied to CRUD API resources, on top of the provider's default_tags |

`dynamodb_gsi1_name` defaults to `gsi1-group-bindings`, matching the
`global_secondary_index` block in `terraform/dynamodb.tf`. If you ever
renamed the index, confirm with `aws dynamodb describe-table --table-name
y62db-config-rule-catalog` before applying.

## References

- [REST API Tutorial — Resource Naming](https://restfulapi.net/resource-naming/)
- [AWS API Gateway Lambda proxy integration](https://docs.aws.amazon.com/apigateway/latest/developerguide/set-up-lambda-proxy-integrations.html)
- [DynamoDB single-table design](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/bp-general-nosql-design.html)
- [DynamoDB conditional writes](https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/WorkingWithItems.html#WorkingWithItems.ConditionalUpdate)
- [RFC 7231 — HTTP/1.1 Semantics and Content](https://www.rfc-editor.org/rfc/rfc7231)
