# Y62DB Bindings CRUD API — Technical Blueprint

**Purpose of this document:** disaster recovery, not a tutorial. If all
session history and working memory of this initiative were lost, this file
alone should be enough to understand *why* things are built the way they
are, *what* exists today, *what state it's in*, and *what to do next* — for
you or anyone else picking this back up cold.

Last updated: 2026-08-02, after applying Cognito authentication to real AWS
and fully verifying the CRUD API end-to-end with a real bearer token (see
§12.2).

---

## 1. What Y62DB is

Y62DB is the catalog and control-plane data layer for curated AWS Config
managed rule metadata, parameter values, scope values, and internal
compliance "flavors." It exists to separate baseline AWS-managed rule
inventory from organization-specific configuration choices, so future
tooling can generate consistent conformance packs, rule bundles, and policy
outputs from one durable source of truth. (See the repo's own top-level
`README.md` for the full mission statement.)

The core modeling idea, from `schemas/access-patterns.md` (the authoritative
design doc, predates this CRUD work):

- One **canonical rule profile** per AWS Config managed rule.
- Many **bindings** — organization-group-specific "flavors" of that same
  rule (different parameter values, scope, activation state) — without
  duplicating the rule definition itself.
- A rule can have many bindings (one per group); a group can have many
  rule bindings. Both directions need to be queryable.

### Entity types (single-table design, `schemas/access-patterns.md`)

| Entity | pk | sk | Notes |
|---|---|---|---|
| `RULE_PROFILE` | `RULE#<rule_id>` | `PROFILE#<rule_id>` | Canonical managed-rule record |
| `PARAMETER_DEF` | `RULE#<rule_id>` | `PARAMDEF#<parameter_name>` | Allowed/known parameter metadata |
| `SCOPE_DEF` | `RULE#<rule_id>` | `SCOPEDEF#<scope_name>` | Valid scope guidance |
| `RULE_BINDING` | `RULE#<rule_id>` | `GROUP#<group_id>#BINDING#<binding_id>` | **The only entity type this CRUD API manages.** `gsi1pk=GROUP#<group_id>`, `gsi1sk=RULE#<rule_id>#BINDING#<binding_id>` |
| `ORG_GROUP` | `GROUP#<group_id>` | `PROFILE#<group_id>` | Internal group metadata |
| `AUDIT_EVENT` | `RULE#<rule_id>` | `AUDIT#<timestamp>#<event_id>` | Immutable change history |

Terraform's job, per that same doc, is infrastructure "underlayment" only
(table, keys, indexes, encryption, recovery, outputs) — **not** ownership of
mutable catalog rows. Rows are meant to come from loaders, CRUD tools, or
application logic. This CRUD API is exactly that: an application-logic layer
for the `RULE_BINDING` entity type, nothing else.

---

## 2. Why there are two Terraform designs in this repo

Git history (oldest → newest) explains the fork:

1. **Root module — legacy, two-table design.** `dynamodb.tf` at the repo
   root creates `config_rules` (hash key `rule_id`) and
   `config_rule_parameters` (hash key `rule_id`, range key
   `parameter_name`). This was the *original* implementation, fed by
   `loader/loader.py`, which parses AWS managed-rule metadata out of
   `config-rules-all/vendor/niaid/managed_rules_*.tf` (a separate private
   repo) via `python-hcl2` and bulk-writes it in. **This is the only design
   actually wired to Terraform Cloud** — `terraform.tf` at the root has the
   `cloud { organization = "RSHL2136", workspaces { name = "Y62DB" } }`
   block.
2. **`terraform/` subfolder — single-table redesign.** Added later
   (`aabb12a Add Y62DB Terraform underlayment and schema scaffolding`) to
   implement the `schemas/access-patterns.md` model above: one table
   (`y62db-config-rule-catalog`) with `pk`/`sk` and a `gsi1-group-bindings`
   GSI. **This subfolder has no `cloud{}`/backend block at all** — it was
   applied once, locally, by hand (there's a committed
   `.terraform.lock.hcl` but no committed state file). It is *not* under
   Terraform Cloud management today.
3. `loader/seeding1.json` + `seeding1.bash` seed real `RULE_BINDING` data
   into the single table — this is the live, in-use data path. The seeded
   example: `pk=RULE#access-keys-rotated`,
   `sk=GROUP#corp#BINDING#default`, `gsi1pk=GROUP#corp`,
   `gsi1sk=RULE#access-keys-rotated#BINDING#default`,
   `payload={maxAccessKeyAge: 60, status: "ACTIVE", version: 1}`.

**Net effect:** the real, seeded, in-use table (`y62db-config-rule-catalog`)
exists in AWS but is *not* in the Terraform Cloud workspace's state. The
Terraform Cloud workspace's state currently only "owns" the legacy
`config_rules`/`config_rule_parameters` tables. Whether those legacy tables
still exist and are still used in AWS was never confirmed — this question
was asked once and skipped by the user; treat as an open item (see §7).

These two designs are **not** competing implementations of the same thing —
they're base-catalog (rule/parameter/scope metadata, never built out beyond
the two placeholder tables) vs. extension-layer (bindings, fully built and
seeded). This CRUD API targets the extension layer, which is also the only
one with real data.

---

## 3. Scope decision: bindings only

Confirmed explicitly by the user: "crud-enable Y62DB" means CRUD on the
`RULE_BINDING` entity type only. Rule profiles, parameter definitions, scope
definitions, org-group metadata, and audit events are **out of scope** for
this API and untouched by it.

---

## 4. What was built

### 4.1 File inventory (all additive except one)

| Path | Status | Purpose |
|---|---|---|
| `api/src/handler.py` | new | Lambda entry point; routes on `(httpMethod, resource)` |
| `api/src/bindings/{list_by_rule,create,get,update,delete,list_by_group}.py` | new | One module per route, each validates input then calls `common/dynamodb.py` |
| `api/src/common/dynamodb.py` | new | All DynamoDB access; key-building helpers; optimistic locking logic |
| `api/src/common/response.py` | new | Standardized success/error envelope |
| `api/src/common/validation.py` | new | Declarative request schema validation (`Field`, `Schema`, `@validate`) |
| `api/src/common/exceptions.py` | new | `ApiError` hierarchy: `ValidationError` (400), `NotFoundError` (404), `ConflictError` (409) |
| `api/tests/*` | new | Pytest suite, 14 tests, uses `moto` to mock DynamoDB — no AWS account needed to run |
| `api/README.md` | new | Full API contract: request/response shapes, status codes, curl examples |
| `crud_api_variables.tf` | new | All new variables for this stack (`crud_api_name`, `dynamodb_table_name`, `dynamodb_gsi1_name`, `lambda_runtime`, `lambda_timeout`, `lambda_memory_size`, `log_retention_days`, `tags`) |
| `crud_api_dynamodb.tf` | new | `data "aws_dynamodb_table"` read-only lookup + `local.dynamodb_table_arn`/`local.dynamodb_gsi1_arn` |
| `crud_api_iam.tf` | new | Lambda execution role, least-privilege DynamoDB policy, basic-execution attachment |
| `crud_api_lambda.tf` | new | `archive_file` zip of `api/src`, CloudWatch log group, the Lambda function itself |
| `crud_api_gateway.tf` | new | Full REST API: resources, methods, integrations, CORS OPTIONS handling, deployment, stage, Lambda invoke permission |
| `crud_api_outputs.tf` | new, later modified | `api_base_url`, `lambda_function_name`, `dynamodb_table_name`, `dynamodb_table_arn`, plus `cognito_user_pool_id`/`cognito_user_pool_client_id` (added §12.1) |
| `crud_api_cognito.tf` | new (§12.1) | Cognito User Pool + public app client (no secret, SRP auth) + `aws_api_gateway_authorizer` (`COGNITO_USER_POOLS`) shared by both the API and the future Amplify frontend's Auth category |
| `docs/policies/tfc-run-role-additions.json` | new (§12.1) | Ready-to-attach IAM policy JSON for the TFC run role — see §8.1 |
| `terraform.tf` | **modified in place** | Added `archive` provider (`hashicorp/archive ~> 2.4`) to the existing `required_providers` block. `cloud{}` block untouched. |

Nothing else in the repo was touched — `dynamodb.tf`, `locals.tf`,
`variables.tf`, `outputs.tf`, `providers.tf` at the root, and everything
under `terraform/`, are exactly as they were before this work.

### 4.2 Why a `data` source, not a `resource`, for the table

`crud_api_dynamodb.tf`:

```hcl
data "aws_dynamodb_table" "rule_catalog" {
  name = var.dynamodb_table_name  # "y62db-config-rule-catalog"
}

locals {
  dynamodb_table_arn = data.aws_dynamodb_table.rule_catalog.arn
  dynamodb_gsi1_arn  = "${data.aws_dynamodb_table.rule_catalog.arn}/index/${var.dynamodb_gsi1_name}"
}
```

This was the deliberate "fast path" decision: since the real table isn't in
this (or any) Terraform Cloud state, the CRUD stack must never attempt to
create or manage it — that would either fail (name collision) or, worse,
silently adopt/orphan the real data. A read-only data lookup gets the ARN
for IAM scoping without taking ownership.

### 4.3 IAM — least privilege, scoped to exactly this table + index

`crud_api_iam.tf`:

```hcl
resource "aws_iam_role_policy" "crud_api_lambda_dynamodb" {
  name = "${var.crud_api_name}-dynamodb-access-${var.environment}"
  role = aws_iam_role.crud_api_lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
      ]
      Resource = [
        local.dynamodb_table_arn,
        local.dynamodb_gsi1_arn,
      ]
    }]
  })
}
```

No `CreateTable`/`UpdateTable`/`DeleteTable`, no wildcard resource ARNs.
Plus `AWSLambdaBasicExecutionRole` for CloudWatch Logs.

### 4.4 API surface

Single Lambda (`crud_api`), fronted by one REST API with three resource
paths, all `AWS_PROXY` to the same function:

```
GET    /rules/{ruleId}/bindings                    list every group a rule is bound to
POST   /rules/{ruleId}/bindings                     create a binding (409 if it already exists)
GET    /rules/{ruleId}/bindings/{group}/{binding}   read one binding
PUT    /rules/{ruleId}/bindings/{group}/{binding}   full replace, optimistic-locked (see 4.5)
DELETE /rules/{ruleId}/bindings/{group}/{binding}   remove a binding
GET    /groups/{group}/bindings                     list every rule bound to a group (via gsi1)
```

Every route also has an `OPTIONS` method (API Gateway `MOCK` integration)
for CORS. Standard response envelope (`api/src/common/response.py`):

```json
// success
{ "data": { ... } }
// error
{ "error": { "code": "not_found", "message": "...", "details": {...}, "request_id": "..." } }
```

Status codes: `200` read/update, `201` created, `204` deleted,
`400` validation, `404` not found / unknown route, `409` conflict
(duplicate create, or stale `expected_version` on update), `500` unhandled.

Full request/response schemas and curl examples are in `api/README.md` —
treat that file as the canonical API contract; this blueprint only
summarizes it.

### 4.5 Optimistic locking on `PUT`

Added specifically because `schemas/access-patterns.md` lists `version` as
a `RULE_BINDING` field and the original scaffold's README called out
"update a binding with optimistic locking using a version field" as a
suggested access pattern. Without this, two concurrent editors could
silently clobber each other's changes.

Request body for `PUT`:

```json
{ "payload": { "status": "INACTIVE", "version": 2, "maxAccessKeyAge": 90 }, "expected_version": 1 }
```

`expected_version` is the version the caller last read. Server-side
(`api/src/common/dynamodb.py::update_binding`):

```python
_table.put_item(
    Item=item,
    ConditionExpression="attribute_exists(pk) AND payload.version = :expected_version",
    ExpressionAttributeValues={":expected_version": expected_version},
)
# ConditionalCheckFailedException -> ConflictError (409), tells the caller
# to refetch and retry.
```

This is a genuine conditional write (not a read-then-write race) — the
DynamoDB condition expression is what actually prevents the lost update.

### 4.6 Lambda config

`crud_api_lambda.tf`: Python 3.12, 256 MB, 10s timeout, code zipped
straight from `api/src/`, two env vars:

```
CONFIG_RULE_CATALOG_TABLE = y62db-config-rule-catalog   (from the data source)
CONFIG_RULE_CATALOG_GSI1  = gsi1-group-bindings          (var.dynamodb_gsi1_name)
```

**Gotcha to remember:** `common/dynamodb.py` has a hardcoded fallback
`GSI1_NAME = os.environ.get("CONFIG_RULE_CATALOG_GSI1", "gsi1")` — the
fallback value `"gsi1"` is *wrong* (the real index is
`gsi1-group-bindings`). This only matters if the Lambda is ever invoked
without its Terraform-set environment variables (e.g. local testing without
`conftest.py`'s fixtures) — in the deployed stack the env var is always set
correctly, so this is safe, just worth knowing about if you ever refactor
this file.

---

## 5. Terraform provider change

`terraform.tf`, the only modified (not new) file, added:

```hcl
archive = {
  source  = "hashicorp/archive"
  version = "~> 2.4"
}
```

to the existing `required_providers` block, needed for
`data "archive_file"` (the Lambda zip step). The `cloud { organization =
"RSHL2136", workspaces { name = "Y62DB" } }` block is byte-for-byte
unchanged.

---

## 6. Validation performed (all local, nothing touched real AWS or real TFC state)

- **`terraform validate`**: since the repo's `cloud{}` block requires
  Terraform Cloud login (not available in the sandbox this was built in),
  validation was done by *temporarily* deleting the `cloud{}` block,
  running `terraform init`/`terraform validate` against a local backend,
  confirming `Success!`, then restoring the exact original block before
  committing. This override was never committed — if you ever see a
  `backend "local"` block or a missing `cloud{}` block in a commit, that's
  a mistake, not intentional. Re-run and re-confirmed `Success!` after
  adding `crud_api_cognito.tf` (§12.1), same technique.
- **`pytest`**: 14/14 tests pass in `api/tests/` using `moto` to mock
  DynamoDB (`conftest.py` builds a table with the same `pk`/`sk`/`gsi1`
  schema as production). Includes a dedicated test that a stale
  `expected_version` on `PUT` returns `409` and leaves the stored item
  unchanged.
- **Not yet done, and can't be done without more access:** an actual
  `terraform plan`/`apply` against the real Terraform Cloud workspace, or
  a live HTTP call against a deployed API Gateway stage. Neither is
  possible from this environment — no Terraform Cloud credentials/connector
  exist here.

---

## 7. Current status as of this document

- **Committed and pushed** to `rtrivgreg/Y62DB`, `main` branch, commit
  `779dd7f` (on top of `e400dfd`).
- **APPLIED (2026-08-02).** The IAM policy in
  `docs/policies/tfc-run-role-additions.json` was attached to the TFC run
  role and a real `plan`/`apply` succeeded in the `RSHL2136`/`Y62DB`
  workspace. This stack is now live in AWS:
  - `api_base_url` = `https://3lkxt728eh.execute-api.us-east-1.amazonaws.com/dev`
  - `lambda_function_name` = `y62db-rule-catalog-api-dev`
  - `cognito_user_pool_id` = `us-east-1_5OUP1L4hf`
  - `cognito_user_pool_client_id` = `2eruh11a9kc2lbdd286q282ofb`
  - Confirmed **zero diff** on `config_rules`/`config_rule_parameters`
    (both showed as no-op in the apply) and on the real
    `y62db-config-rule-catalog` table (still a read-only `data` source).
- **API authentication: Cognito, applied and verified live.** All six
  data-touching methods require `authorization = "COGNITO_USER_POOLS"`
  via `aws_api_gateway_authorizer.cognito` (`crud_api_cognito.tf`, §12.1).
  Verified directly against the live endpoint: no `Authorization` header
  → `401 {"message":"Unauthorized"}`; garbage token → same `401`;
  `OPTIONS` preflight → `200` with no auth required. Closes §8.2 for real,
  not just on paper.
- **Legacy tables confirmed live — owned by a separate application,
  DO NOT TOUCH.** Verified directly against AWS (`aws-dynamodb-scan`,
  `us-east-1`): `config_rules` has **801 items**, `config_rule_parameters`
  has **669 items**, both in the old flat schema (no
  `pk`/`sk`/`entity_type`). Neither is read by anything in this repo's
  `api/` — **but they are an essential component of a separate Python
  application that is not part of the Y62DB initiative** (confirmed by the
  repo owner 2026-08-02). They must be retained as-is; not archived, not
  deleted, not modified, regardless of anything Y62DB does. Y62DB's own
  `loader/loader.py` now independently seeds equivalent data into
  `y62db-config-rule-catalog` as `RULE_PROFILE`/`PARAMETER_DEF` items
  (802 + 670, verified via direct scan/query, §11) — that is a parallel,
  Y62DB-owned copy for the single-table schema, not a migration that
  supersedes or retires the legacy tables. The two independent systems now
  each have their own copy of similar data; keep them both.
- **`terraform/` subfolder still orphaned** from Terraform Cloud state —
  standing drift risk, unrelated to but adjacent to this work.

### Identifiers (carry-forward reference)

| Item | Value | Confidence |
|---|---|---|
| GitHub repo | `rtrivgreg/Y62DB` | confirmed this session |
| Latest commit (this work) | `779dd7f` | confirmed this session |
| Terraform Cloud org | `RSHL2136` | confirmed from `terraform.tf` |
| Terraform Cloud workspace | `Y62DB` | confirmed from `terraform.tf` |
| Real DynamoDB table | `y62db-config-rule-catalog`, `us-east-1` | confirmed from `terraform/dynamodb.tf` + seed data |
| GSI name | `gsi1-group-bindings` | confirmed from `terraform/dynamodb.tf` |
| AWS account | `418295699841` | **from prior session notes — not reverified this session; confirm before relying on it** |
| AWS IAM user | `alpha` | **from prior session notes — not reverified this session; confirm before relying on it** |

---

## 8. Open decisions and risks — needs a human

1. **OIDC run-role permissions.** The Y62DB TFC workspace's run role has
   only ever needed DynamoDB table permissions. This plan now needs
   `lambda:*`, scoped `iam:CreateRole`/`PutRolePolicy`/`AttachRolePolicy`/
   `PassRole`/etc. on the `y62db-rule-catalog-api-*` role name prefix,
   `apigateway:*`, `logs:CreateLogGroup`/`PutRetentionPolicy`,
   `dynamodb:DescribeTable`, and (new, for §12.1) `cognito-idp:CreateUserPool`/
   `CreateUserPoolClient`/`DescribeUserPool*`/`UpdateUserPool*`/tagging
   actions. A ready-to-attach policy document with all of the above is at
   `docs/policies/tfc-run-role-additions.json` — attach it to the run role
   (there is no Terraform Cloud connector available to do this
   automatically; it must be done by hand in IAM, since the OIDC run role
   itself lives outside this stack's own state). If missing, the plan will
   apply the easy resources and then fail partway through. **Do this before
   triggering apply.**
2. **API authentication — RESOLVED and APPLIED.** Cognito User Pool +
   authorizer chosen (§12.1) specifically because it doubles as the
   Amplify frontend's Auth category later — one identity source for both
   the API and the UI. Live and verified rejecting unauthenticated
   requests (see §7).
3. **Legacy two-table fate — RESOLVED, no action needed.** `config_rules`/
   `config_rule_parameters` are owned by a separate, unrelated Python
   application and must be retained permanently (confirmed by the repo
   owner 2026-08-02). This is not a Y62DB decision to make. Y62DB has its
   own equivalent data now in `y62db-config-rule-catalog` (§11) and has no
   further business with these two tables or their Terraform resources —
   don't revisit archiving/deleting them under this initiative.
4. **`terraform/` subfolder reconciliation.** The real table's own
   definition still isn't under any Terraform Cloud state. Bringing it
   under management (e.g. `terraform import`) is a bigger, riskier future
   project — not attempted here on purpose.

---

## 9. Next steps (in order)

1. Fix the OIDC role permissions (item 1 above).
2. Trigger `terraform plan` in the `RSHL2136`/`Y62DB` TFC workspace on the
   `main` branch (commit `779dd7f` or later). **Verify the plan shows only
   additions** (Lambda, IAM role/policy, API Gateway resources, CloudWatch
   log group, archive provider) and **zero diff** on
   `config_rules`/`config_rule_parameters`.
3. Apply.
4. Grab the `api_base_url` output; run a full CRUD sequence against the
   live endpoint (`POST` → `GET` → list-by-rule → list-by-group → `PUT`
   with correct `expected_version` → `PUT` again with a stale version,
   expect `409` → `DELETE`).
5. Check CloudWatch Logs for the new Lambda for anything the `moto`-based
   tests couldn't catch (real IAM, real table, real GSI).
6. Decide and implement API auth (§8.2).
7. Revisit §8.3/§8.4 when there's time for a more deliberate reconciliation
   effort — not urgent, not safe to rush.

---

## 10. How to resume from zero context

1. Read this document top to bottom before touching anything.
2. `git log --oneline` in the repo — if `HEAD` is still `779dd7f`, nothing
   has changed since this was written. If it's moved on, read the newer
   commit messages first; they should explain themselves.
3. Check the Terraform Cloud workspace's run history
   (`app.terraform.io`, org `RSHL2136`, workspace `Y62DB`) to see whether
   §9 steps 2–3 have happened yet — this document can't know that, only
   you can check it live.
4. `api/README.md` is the canonical API contract — read it for exact
   request/response shapes before building any client against this API.
5. `schemas/access-patterns.md` is the canonical data-model doc — read it
   before touching anything outside the `RULE_BINDING` entity type.
6. If anything in this document conflicts with what you find in the repo,
   trust the repo — this file describes intent and history, the code is
   ground truth.

---

## 11. Loader rewrite: seeding the single table (2026-08-02)

### Why this happened

The original `loader/loader.py` wrote flat rows into the legacy
`config_rules`/`config_rule_parameters` tables — a design that predates
`schemas/access-patterns.md`'s single-table model and doesn't fit it.
Direct AWS verification (`aws-dynamodb-scan` against both tables in
`us-east-1`) confirmed they're live and populated: **801 items** in
`config_rules`, **669 items** in `config_rule_parameters`, both using the
old flat schema (plain `rule_id`/`parameter_name` columns, no
`pk`/`sk`/`entity_type`). Nothing in `api/` reads them — the CRUD API only
touches `RULE_BINDING` items in `y62db-config-rule-catalog` — so they're
orphaned from the application's perspective but not empty stubs; deleting
them without migrating their data first would have been a real loss.

### What changed

`loader/loader.py` now writes `RULE_PROFILE` and `PARAMETER_DEF` items
directly into the single table (`--table` replaces the old
`--rules-table`/`--parameters-table` flags):

```
RULE_PROFILE
  pk = RULE#<rule_id>          sk = PROFILE#<rule_id>
  entity_type, rule_id, source_identifier, description, severity, scopes,
  managed_rule

PARAMETER_DEF
  pk = RULE#<rule_id>          sk = PARAMDEF#<parameter_name>
  entity_type, rule_id, parameter_name, data_type, required, default_value,
  source_variable, placeholder_value
```

Key fix: the old script baked `RULE#` directly into the logical `rule_id`
field (e.g. `rule_id = "RULE#access-keys-rotated"`, visible today in the
real `config_rules` scan output). The rewrite keeps `rule_id` as the plain
slug and only adds the `RULE#` prefix when constructing `pk`/`sk` — matching
the convention the CRUD API already uses (`_pk`/`_gsi1sk` helpers in
`api/src/common/dynamodb.py`). Mixing the two conventions in the same table
would have made every future `Query(pk=...)` inconsistent.

**Deliberately deferred:** `SCOPE_DEF` items. `access-patterns.md` defines
a `SCOPE_DEF` entity type for scope guidance, but doesn't specify how it
maps from this source data, and the parsed data only carries one
resource-type list per rule with no extra guidance content. Rather than
invent a shape, parsed scope values are kept as a `scopes` attribute on
`RULE_PROFILE` for now — the data isn't lost, just not split out yet.

### Validation performed

Unit-level: the rewrite was validated against a small synthetic fixture
(`loader/tests/fixtures/`, two rules, one with a parameter block) +
`loader/tests/test_loader.py` (6 tests — rule-id shape, item shape for both
entity types, empty-parameter case, DynamoDB type-mapping for sets/bools,
`--rule-limit`). All 6 passed.

**Real migration: done (2026-08-02), from the user's machine.** The loader
was run for real against the actual `config-rules-all` vendor files
(`~/code/t/config-rules-all`) and wrote directly into
`y62db-config-rule-catalog` in `us-east-1`:

```
rule_profile_items=802 parameter_def_items=670
```

Independently verified via direct DynamoDB scans/queries afterward:

- **802 `RULE_PROFILE` items**, all with unique `pk`s (one per rule, no
  duplicates, no gaps vs. the loader's own reported count).
- **670 `PARAMETER_DEF` items** across **412 distinct rules** (87 of those
  rules have more than one parameter; the rest have exactly one) — totals
  match the loader's own output exactly.
- `Query(pk=RULE#access-keys-rotated)` returns all three items together —
  the pre-existing `RULE_BINDING` (`GROUP#corp#BINDING#default`), plus the
  newly-written `RULE_PROFILE` and `PARAMETER_DEF` — confirming access
  pattern #1 in `access-patterns.md` works end-to-end and that seeding did
  not disturb the existing binding data.

Note: 802/670 is one more than each of the legacy tables' counts (801
rules / 669 parameters, §7) — the legacy tables are simply stale by one
rule relative to the current `config-rules-all` source, not a loader bug.

### Next steps for this specific track

1. ~~Run against the real `config-rules-all` source and seed
   `y62db-config-rule-catalog`.~~ **Done and verified**, see above.
2. Spot-check a few more rules beyond `access-keys-rotated` (ideally ones
   with multiple parameters, and at least one with zero parameters) if a
   higher confidence bar is wanted before treating this as fully proven.
3. **Do not archive or delete `config_rules`/`config_rule_parameters`.**
   Despite not being read by this repo's `api/`, they belong to a separate,
   unrelated Python application (confirmed by the repo owner 2026-08-02)
   and must be retained permanently. Y62DB's copy of this data in
   `y62db-config-rule-catalog` is additional, not a replacement — treat
   §8.3 as closed, not as a future cleanup task.

---

## 12. Form-UI roadmap (decided 2026-08-02, work starting with §12.1)

### Why this track exists

The end goal is a form-based UI for managing `RULE_BINDING`s, hosted on AWS
Amplify. As of 2026, Amplify Gen 1 (and its drag-and-drop "Studio" form
builder, which could auto-generate React forms from an arbitrary REST API)
is heading into maintenance mode; Amplify Gen 2's auto-generated CRUD forms
only work against Amplify's own `a.model()` data layer (its own
AppSync+DynamoDB), not a hand-rolled single-table REST API like this one.
Rebuilding the data layer to fit Amplify's model would duplicate/replace
infrastructure that's already built and Terraform-managed here — not worth
it for one form and a browse view.

**Decision: Amplify Gen 2 for Hosting + Auth only.** The existing
API Gateway + Lambda stack stays exactly as designed, registered with the
frontend via Amplify's "use existing AWS resources" REST API pattern
(`Amplify.configure({ API: { REST: { ... } } })` pointing at `api_base_url`).
Forms are hand-built with `@aws-amplify/ui-react` field components, not
generated by a form builder.

### Decisions locked in

| Question | Decision |
|---|---|
| Sequencing | Backend first — fix §8.1 (OIDC permissions), `terraform apply`, verify CRUD end-to-end and Cognito auth actually works, *then* start the frontend. Building a UI against a backend that's never been applied would mean debugging both layers blind at once. |
| v1 form scope | `RULE_BINDING` create/edit/delete (the only CRUD entity this API has) **plus** a read-only browser for `RULE_PROFILE`/`PARAMETER_DEF` — lets a user look up what parameters a rule expects before creating a binding for it. Both are already fully supported by the existing API surface (§4.4) and real seeded data (§11); no backend changes needed for this scope. |
| Repo layout | Single repo. New `ui/` subfolder, not a separate repo — matches this project's existing single-repo, IaC-heavy style. When Amplify Hosting is connected, use its monorepo "app root" setting pointed at `ui/` rather than the repo root. |

### §12.1 — Done this session (not yet applied to real AWS)

- `crud_api_cognito.tf`: Cognito User Pool (`aws_cognito_user_pool`), a
  public app client with no secret (`aws_cognito_user_pool_client`, SRP +
  refresh-token auth flows only — matches Amplify's `<Authenticator>`
  component, no OAuth Hosted UI/callback URLs needed), and
  `aws_api_gateway_authorizer.cognito` (`COGNITO_USER_POOLS` type).
- `crud_api_gateway.tf`: all six data-touching methods
  (`rule_bindings_get/post`, `rule_binding_get/put/delete`,
  `group_bindings_get`) switched from `authorization = "NONE"` to
  `COGNITO_USER_POOLS` + `authorizer_id`. All `OPTIONS` methods
  deliberately left at `NONE` — CORS preflight requests aren't
  authenticated by browsers.
- `crud_api_outputs.tf`: added `cognito_user_pool_id` and
  `cognito_user_pool_client_id` outputs — the future `ui/` app's
  `Amplify.configure()` call needs both.
- `docs/policies/tfc-run-role-additions.json`: the exact IAM policy JSON
  to attach to the TFC run role, folding in the pre-existing §8.1
  requirements plus the new `cognito-idp:*` actions this file needs.
- Validated with the same temporary-`cloud{}`-removal `terraform
  validate` technique as §6 — `Success!`. No `apply` attempted (same
  reason as always: no Terraform Cloud credentials/connector in this
  environment).

### Next steps for this track (in order)

1. ~~Attach `docs/policies/tfc-run-role-additions.json` to the TFC run role.~~
   **Done.**
2. ~~`terraform plan`/`apply` in the `RSHL2136`/`Y62DB` workspace.~~ **Done
   (2026-08-02)** — applied with zero diff on `config_rules`/
   `config_rule_parameters` and the real `y62db-config-rule-catalog` table.
   See §7.
3. ~~Create at least one real Cognito user and confirm a token from that
   user is accepted, and that requests without a token are rejected.~~
   **Done.** See §12.2.
4. ~~Run the full CRUD sequence again, now with a real bearer token
   attached.~~ **Done, all 8 cases pass.** See §12.2.
5. Scaffold `ui/`: `npm create amplify@latest` for Auth-only Gen 2 backend,
   Vite + React, `aws-amplify` + `@aws-amplify/ui-react`. **← current step.**
6. Configure the existing-REST-API pattern in the app pointing at
   `api_base_url`; wrap the app in `<Authenticator>` using the real
   `cognito_user_pool_id`/`cognito_user_pool_client_id` outputs.
7. Build the v1 screens: bindings CRUD form + rule/parameter browser.
8. Connect Amplify Hosting to a git branch (monorepo app root = `ui/`) for
   CI/CD.
9. Decide whether the Amplify app resource itself
   (`aws_amplify_app`/`aws_amplify_branch`) should also be
   Terraform-managed to match this project's IaC-first approach, or left
   to Amplify's own Console/CLI-managed stack. Not decided yet — revisit
   once step 8 is imminent.

### §12.2 — Full CRUD verification with a real bearer token (2026-08-02)

A test Cognito user (`testuser`) was created and
`aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH` used to
obtain a real `IdToken` (not the `AccessToken` — API Gateway's
`COGNITO_USER_POOLS` authorizer requires the ID token when the method has
no OAuth scopes configured, which is the case here; the access token lacks
the `aud` claim the authorizer checks). `USER_PASSWORD_AUTH` was added to
`explicit_auth_flows` in `crud_api_cognito.tf` purely for this CLI
smoke-testing — the real Amplify frontend uses `USER_SRP_AUTH` instead.

Every route and edge case in the API contract (`api/README.md`) was
exercised directly against the live endpoint using a disposable
`rules/access-keys-rotated/bindings/smoke-test/crud-check` record (cleaned
up afterward, no test data left behind):

| # | Call | Expected | Result |
|---|---|---|---|
| 1 | `POST .../bindings` (create) | `201` | ✅ |
| 2 | `POST .../bindings` (duplicate) | `409 conflict` | ✅ |
| 3 | `GET .../bindings/{group}/{binding}` | `200`, matches created payload | ✅ |
| 4 | `PUT ...` with stale `expected_version` | `409 conflict` | ✅ |
| 5 | `PUT ...` with correct `expected_version` | `200`, `payload.version` bumped | ✅ |
| 6 | `GET /groups/{group}/bindings` (gsi1 query) | `200`, one item, updated payload | ✅ |
| 7 | `DELETE .../bindings/{group}/{binding}` | `204`, empty body | ✅ |
| 8 | `GET` the deleted binding | `404 not_found` | ✅ |

Also reconfirmed at the top of this session, before the table above:
`GET /rules/access-keys-rotated/bindings/corp/default` (real seeded data,
read-only) → `200` with the real `maxAccessKeyAge: 60` record; no
`Authorization` header → `401`; garbage token → `401`; `OPTIONS` → `200`
unauthenticated.

**Conclusion: the entire stack — Cognito auth, API Gateway authorizer,
Lambda routing/validation, DynamoDB conditional writes and GSI query — is
live, correct, and fully verified end-to-end.** Roadmap items 0 (unblock
backend) and 1 (decide + verify auth) are closed. Next up: item 2,
scaffolding `ui/` (§12.1 step 5).
