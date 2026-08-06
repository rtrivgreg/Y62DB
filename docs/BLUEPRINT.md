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
5. ~~Scaffold `ui/`.~~ **Done (2026-08-02).** See §12.3.
6. ~~Configure the existing-REST-API pattern in the app pointing at
   `api_base_url`; wrap the app in `<Authenticator>`.~~ **Done.** See §12.3.
7. ~~Build the bindings CRUD form.~~ **Done (2026-08-02).** See §12.4. The
   `RULE_PROFILE`/`PARAMETER_DEF` read-only browser is still open.
8. Connect Amplify Hosting to a git branch (monorepo app root = `ui/`) for
   CI/CD. **← current step.**
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

### §12.3 — `ui/` scaffolded (2026-08-02)

Vite + React + TypeScript app, no separate Amplify Gen 2 backend project
(no `amplify/` folder, no `npx ampx sandbox`) — both Auth and the REST API
already exist and are Terraform-managed at the repo root, so this app just
points Amplify's client libraries at them directly, per Amplify's
documented "use existing AWS resources" pattern.

```
ui/
├── src/
│   ├── amplify-config.ts        # Amplify.configure() -> real user pool + client ID
│   ├── api/bindingsApi.ts       # fetch() wrapper, 1:1 with api/README.md's routes
│   ├── pages/BindingsBrowser.tsx # read-only list-by-rule / list-by-group screen
│   ├── App.tsx                  # <Authenticator> wrapper + header/sign-out
│   └── main.tsx
├── package.json                 # aws-amplify, @aws-amplify/ui-react, Vite 5, React 18
└── README.md                    # what's real vs. still to build, why plain fetch()
```

Key decisions:

- **`amplify-config.ts` hardcodes the real applied identifiers**
  (`cognito_user_pool_id`, `cognito_user_pool_client_id`, `api_base_url`
  from §7) — no `.env` file yet; fine for a single-environment scaffold,
  revisit if a second (e.g. staging) environment is ever needed.
- **Plain `fetch()` in `bindingsApi.ts`, not Amplify's `API` (REST)
  category** — the API's `COGNITO_USER_POOLS` authorizer expects the raw
  Cognito ID token in `Authorization`, not IAM SigV4 signing (the
  category's default for REST). `fetchAuthSession()` pulls the ID token
  from the current `<Authenticator>` session and it's attached directly.
- **`BindingsBrowser.tsx` is read-only on purpose** — it exists to prove
  the auth + API wiring works end-to-end from a real browser session, not
  as the finished v1 UI. Create/edit/delete forms and the
  `RULE_PROFILE`/`PARAMETER_DEF` browser are still §12.1 step 7.

**Validation performed:** `npm install` (222 packages) and `npm run
build` (`tsc --noEmit` + `vite build`) both succeed cleanly — no type
errors, production bundle builds.

**Interactive verification (2026-08-02, later same day):** the user ran
`npm install && npm run dev` on their own Mac (after installing Node via
Homebrew — CloudShell has no browser-preview mechanism for a dev server,
unlike Google/Azure Cloud Shell, so local was the right call), opened
`http://localhost:5173`, signed in as `testuser` through the real
`<Authenticator>` flow, and searched `access-keys-rotated` by rule ID —
**2 binding(s) found**, confirming the full path (Vite dev server → Amplify
Auth → Cognito → API Gateway authorizer → Lambda → DynamoDB) works from an
actual browser, not just `curl`.

### §12.4 — Full CRUD forms built (2026-08-02)

Extended `BindingsBrowser.tsx` and added `components/BindingForm.tsx` to
cover the remaining three operations (create, update, delete) on top of
the existing search/list screen — closing §12.1 step 7's bindings-CRUD
half (the `RULE_PROFILE`/`PARAMETER_DEF` read-only browser is a separate,
still-open piece of that step).

```
ui/src/
├── components/
│   └── BindingForm.tsx      # shared create/edit form (used both ways)
└── pages/
    └── BindingsBrowser.tsx  # search/list + "New binding" + per-row Edit/Delete
```

Key decisions:

- **One form component for both create and edit**, switched on a `mode`
  prop — avoids duplicating the payload/JSON-extra-fields handling. In
  edit mode the identity fields (`rule_id`/`group`/`binding`) are rendered
  disabled since `PUT` replaces `payload` on an existing item, not a
  rename.
- **`payload.version` is never hand-typed on edit** — the form reads the
  `version` off the record that was just listed, sends it as
  `expected_version` (per `api/README.md`'s optimistic-locking contract),
  and computes the new stored version as `+1` automatically. A `409` from
  a stale version is caught and surfaced with a distinct message telling
  the user to re-search before retrying, rather than a generic error.
- **Rule-specific payload keys (e.g. `maxAccessKeyAge`) are edited as a
  freeform JSON object textarea**, since the API's payload schema is
  intentionally open-ended beyond `status`/`version` — the form splits
  `status`/`version` out as first-class fields and merges everything else
  back in as-is on submit.
- **Delete asks for an in-browser confirmation** (`window.confirm`) before
  calling the API, and both create/update/delete re-run the last search
  afterward so the table reflects the live state without a manual
  refresh.

**Validation performed:** `npm install` and `npm run build` (`tsc --noEmit`
+ `vite build`) both succeed cleanly, no type errors. Not yet
interactively verified in a browser against the live API (create/edit/
delete specifically — search/list already was, see above) — worth a quick
pass before moving to Amplify Hosting.

### §12.5 — Typo-tolerant fuzzy search for bindings (2026-08-02)

New feature (not a bug fix): the search box previously required an exact
rule ID or group. It now tolerates typos and separator differences —
e.g. querying `access-keys.rotated` matches `access-keys-rotated`, and a
shortened/typo'd query like `acces` still matches. Requirement clarified
with the user up front: true edit-distance fuzzy matching (not just
substring), with candidates sourced by scanning existing bindings (no
separate rule-catalog endpoint).

**Backend — two new read-only list endpoints** (there's no GSI that
enumerates distinct rule IDs or groups directly, so both do a paginated
full-table `Scan`, deduping on `pk`/`sk` respectively):

```
api/src/
├── common/dynamodb.py     # + list_distinct_rule_ids(), list_distinct_groups()
├── rules/list_ids.py       # GET /rules  -> sorted distinct rule IDs
└── groups/list_ids.py      # GET /groups -> sorted distinct groups
```

`handler.py` gained two `ROUTES` entries for `GET /rules` and
`GET /groups`. `crud_api_iam.tf` gained a `dynamodb:Scan` action on the
Lambda's existing least-privilege policy (documented inline as needed
specifically because no GSI covers this). `crud_api_gateway.tf` gained
full resource/method/integration/CORS wiring for both new routes,
mirroring the existing per-route pattern exactly, plus the deployment's
`triggers`/`depends_on` updated so a redeploy is forced.

A scan-based approach is fine at the table's current size; the endpoint
docstrings note it would need a dedicated GSI or a real rule catalog if
the table grows significantly.

**Frontend — client-side fuzzy matching, then fan-out:**

```
ui/src/
├── fuzzyMatch.ts           # normalize + Levenshtein-based typo-tolerant prefix match
├── api/bindingsApi.ts      # + listAllRuleIds(), listAllGroups()
└── pages/BindingsBrowser.tsx  # search now fetches candidates, fuzzy-filters, fans out
```

Matching algorithm (`fuzzyMatch.ts`): normalize case and collapse
separators (`-`/`_`/`.`/space) on both query and candidate; a candidate
shorter than the query never matches (the query is the more-specific
string — a trailing digit like the `2` in `access-keys-rotated2` is a
meaningful part of a distinct rule ID here, not typo noise); otherwise
compare the query against the same-length prefix of the candidate via
Levenshtein distance, matching within ~20% error (minimum 1). This
reproduces all three examples the user specified: `acces` and
`access-keys.rotated` both match `access-keys-rotated` and
`access-keys-rotated2`, while `access-keys.rotated2` matches only the
longer one.

On search, the UI now fetches the full candidate list (`GET /rules` or
`GET /groups`), fuzzy-filters it against the query, then fans out
`listBindingsForRule`/`listBindingsForGroup` per matched candidate and
merges everything into one results table — shown to the user as a
"Fuzzy-matched rule ID(s)/group(s): ..." line above the table so it's
clear why the same rule ID/group can appear more than once (once per
binding under it).

**Validation performed:**
- `terraform validate` — passes.
- `python -m pytest` in `api/` — 15 passed (12 pre-existing + 3 new tests
  in `api/tests/test_list_ids.py` covering `GET /rules`, `GET /groups`,
  and the empty-table case).
- Fuzzy-match algorithm sanity-checked directly in Node against the
  user's three example queries — all three produce the expected match
  sets.
- `npm run build` (`tsc --noEmit` + `vite build`) — succeeds cleanly, no
  type errors.
- **Applied to live AWS (2026-08-02).** User ran `terraform apply` in
  Terraform Cloud (org `RSHL2136`, workspace `Y62DB`); run confirmed, new
  state version created. Verified post-apply by hitting both new routes
  without an auth token: `GET /rules` and `GET /groups` both return
  `401 {"message":"Unauthorized"}` (the Cognito authorizer rejecting a
  missing token), the same behavior as the pre-existing
  `GET /rules/{ruleId}/bindings` route — confirming both are correctly
  wired end-to-end (API Gateway resource + Cognito authorizer + Lambda
  integration), as opposed to the distinct "Missing Authentication Token"
  error API Gateway returns for a path that doesn't match any deployed
  resource. Not yet interactively verified with a real signed-in token
  against live data (that requires the UI + a Cognito login, which the
  agent doesn't have credentials for) — worth a quick pass in the browser
  before calling this fully done.

### §12.6 — Fix: short-query over-matching + fragile fan-out (2026-08-02)

**Bug found during manual QA:** with two browser tabs open, a search in
one tab returned a huge, nearly-alphabetical match list (~130+ rule IDs)
instead of a small, relevant set — and the user reported it as an error.
This also revealed the live table already holds hundreds of real AWS
Managed Config rule names (e.g. `acm-certificate-expiration-check`,
`alb-desync-mode-check`), not just test fixtures — useful context, but it
meant the fuzzy-match bug below hit a much larger candidate set than any
manual testing so far had exercised.

**Root cause — fuzzy-match algorithm, not tab count:** the ~20%-error
threshold from §12.5 breaks down for short queries. Comparing two
2-character strings that share only their first character already has a
Levenshtein distance of 1 — the same threshold used for 5-character
queries. So a 2-character query like `a2` matched *every* candidate
starting with `a`, regardless of the second character (reproduced
directly in Node before fixing). The two-tab framing was circumstantial:
it likely just made a heavier ~130-request fan-out (see below) more
likely to hit a transient failure.

**Fix 1 (`ui/src/fuzzyMatch.ts`):** added `MIN_FUZZ_LEN = 3`. Queries
shorter than that now require an *exact* same-length prefix match (0
edits) — no Levenshtein tolerance at all — while queries at or above that
length keep the existing ~20%-error behavior from §12.5 unchanged.
Re-verified in Node: all three original user examples (`acces`,
`access-keys.rotated`, `access-keys.rotated2`) still produce the exact
expected match sets; `a2` now correctly matches nothing (no candidate
literally starts with `a2`) instead of ~130 unrelated rules.

**Fix 2 (`ui/src/pages/BindingsBrowser.tsx`), defensive regardless of Fix
1:** the search fan-out used `Promise.all`, so a single failed lookup
among many concurrent ones (plausible with 100+ requests, or two tabs
contending for the same Cognito session) wiped out the *entire* result
set with a generic error. Switched to `Promise.allSettled`: successful
lookups are merged and shown; failures are listed by name in a
non-fatal warning instead of blanking the table. Also added a
`MAX_FANOUT = 40` guardrail — if a query matches more candidates than
that, the UI now asks for a more specific query instead of firing dozens
of API calls at once.

**Validation performed:**
- Reproduced the bug directly in Node against the reported candidate
  pattern before fixing (confirmed `a2`/`ac` matched everything
  `a`-prefixed).
- Re-ran all three §12.5 example queries post-fix — unchanged, correct
  results.
- `npm run build` (`tsc --noEmit` + `vite build`) — succeeds cleanly, no
  type errors.
- No backend changes in this fix, so no Terraform/apply implications —
  this is pushable and effective immediately once pulled, no
  `terraform apply` needed.

### §12.7 — UX fix: broad-match picker instead of a dead-end error (2026-08-02)

**Follow-up report:** searching a common AWS service prefix like `EC2`
or `S3` "crashed" — in practice this was the §12.6 `MAX_FANOUT` guardrail
correctly refusing to fetch 79 rule IDs' worth of bindings at once, but
surfacing that refusal as a hard error with zero results was a dead end
for a perfectly reasonable, legitimately-broad query (there really are
~79 real `ec2-*` rules in the catalog).

**Fix (`ui/src/pages/BindingsBrowser.tsx`):** when the match count
exceeds `MAX_FANOUT`, the UI no longer shows a blocking error. Instead
it renders the full matched-candidate list as clickable buttons; clicking
one fetches and merges in just that candidate's bindings (deduped by
rule/group/binding key), so the user can drill into as many of the
matches as they actually want, in whatever order, without the app ever
auto-firing dozens of concurrent lookups. Narrowing the query still works
as before and returns straight to the automatic fetch-all path once the
match count drops back under the cap.

**Validation performed:** `npm run build` (`tsc --noEmit` + `vite
build`) — succeeds cleanly, no type errors. No backend/Terraform changes.

### §12.8 — Chunk fan-out to protect Lambda concurrency quota (2026-08-02)

**Incident:** on the same day as §12.5–§12.7, AWS sent an
`AWS_SERVICEQUOTAS_INCREASE_REQUEST_FAILED` Health event for account
418295699841 (us-east-1): the Lambda **Concurrent executions** quota
(`L-B99A9384`) hit 100% utilization, and the automatic auto-adjust
increase request AWS tried on the account's behalf was not approved.
The account's applied quota for this value was only **10** (well below
the AWS default of 1,000) — easily saturated by a single broad fuzzy
search, whose fan-out (up to `MAX_FANOUT = 40` matches, more before the
§12.6 fix) fires one Lambda invocation per matched candidate. The timing
lines up with the §12.6 bug report (a pathological short-query match
fanning out ~130 concurrent invocations before that fix shipped),
making it the most likely trigger.

**Remediation (outside this repo):** a manual quota increase to 100 for
`L-B99A9384` was submitted via the Service Quotas console (manual
requests get human review and can succeed even when an auto-adjust
attempt for the same quota didn't).

**Defensive fix (`ui/src/pages/BindingsBrowser.tsx`):** added a
`fetchInBatches()` helper and `FANOUT_BATCH_SIZE = 6` constant. The
fan-out lookup in `runSearch()` now runs matched candidates through this
helper — sequential batches of 6 concurrent lookups each — instead of a
single `Promise.allSettled` over the full match set (up to 40 at once).
Per-item settled outcomes are still returned in original candidate
order, so the existing partial-failure reporting (`failed.join(", ")`)
is unaffected. This caps this feature's contribution to account-level
Lambda concurrency at 6 in-flight invocations regardless of how broad a
match is, independent of whatever the account's applied quota ends up
being after the increase request above.

**Validation performed:** `npm run build` (`tsc --noEmit` + `vite
build`) — succeeds cleanly, no type errors. No backend/Terraform
changes; behavior of the too-broad picker (§12.7) and short-query guard
(§12.6) is unchanged, only the fetch-all path's concurrency pattern
changed.

### §12.9 — Fix: stale async search responses could overwrite newer results (2026-08-02)

**Bug report:** searching "s3" showed 79 results, all `ec2-*`/`ecr-*`/
`ecs-*` rule IDs (zero `s3-*` entries), and clicking a candidate button in
the too-broad picker (§12.7) appeared to do nothing.

**Root cause:** `GET /rules` and `GET /groups` take no query parameters —
every search fires an identical request, so if a user runs a second
search before the first one's request has settled, network timing alone
decides which resolves first. `runSearch()` had no request-cancellation
or staleness guard: whichever response resolved *last* unconditionally
overwrote `matchedCandidates`/`results`/`tooBroad` state, regardless of
which search was fired last. An older, broad search (e.g. a 3-character
query like `ec2`, which — per the §12.6 threshold formula
`max(1, ceil(length*0.2))` — legitimately fuzzy-matches `ecr-*` and
`ecs-*` too, 1 edit away at the same prefix length) resolving after a
newer `s3` search explains the exact symptom: the `s3` search's own
(correct) results were silently discarded and replaced by the stale
search's stragglers. The same unguarded overwrite could also fire after
a candidate-picker click, clearing results the click had just fetched —
explaining "the links do nothing." Reproduced in isolation with a
standalone Node script simulating two same-shaped async calls resolving
out of order: the unguarded version kept the *slower* call's result even
though it was fired first; a generation-counter-guarded version always
kept the most recently *started* call's result regardless of resolve
order.

**Fix (`ui/src/pages/BindingsBrowser.tsx`):** added a
`searchGenerationRef` counter. `runSearch()` increments it at the start
of every call and, after each `await`, bails out before touching state
if the ref no longer matches the generation it captured — i.e. a newer
search has since started. `fetchOneCandidate()` (the picker's per-click
fetch) instead *snapshots* the current generation without incrementing
it: multiple picker clicks from the same search still accumulate into
`results` together (the picker's "click several to build up the table"
UX depends on this), but a click's result is discarded if a brand-new
search has started before it resolves. Net effect: whichever
search/click was *started* most recently always wins, independent of
how the underlying promises actually resolve.

**Validation performed:** standalone Node repro (`repro.mjs`) confirming
the race and the fix's correctness; `npm run build` (`tsc --noEmit` +
`vite build`) — succeeds cleanly, no type errors. No backend/Terraform
changes; the §12.6 fuzzy threshold and §12.7 too-broad picker UX are
unchanged — only response ordering is now guarded.

### §12.10 — Fix: GET /rules leaked catalog-only rules with zero bindings (2026-08-02)

**Bug report:** after §12.9 fixed the search-result race, searching "s3"
correctly returned 30 real `s3-*` AWS Config rule names, but the UI
showed "0 binding(s) found" for all of them and no clickable candidates
at all.

**Root cause:** `list_distinct_rule_ids()` (`api/src/common/dynamodb.py`,
backs `GET /rules`) filtered candidates on `pk.startswith("RULE#")`
alone. That was a safe signal only because, at the time it was written,
`RULE_BINDING` was the *only* entity type in the table using that pk
prefix. The §11 loader rewrite (same day) seeded 802 `RULE_PROFILE`
items (`sk="PROFILE#<ruleId>"`) and 670 `PARAMETER_DEF` items
(`sk="PARAMDEF#<parameterName>"`) into this same table — both also using
`pk="RULE#<ruleId>"`. From that point on, `GET /rules` silently started
returning the *entire* rule catalog (minus items it happened to overlap
with) instead of just rules that actually have a binding, because
nothing checked `sk`. `GET /rules/{ruleId}/bindings` itself was always
correct (it queries by `pk` and only ever returns real `RULE_BINDING`
items) — so the catalog-only candidates the picker showed genuinely had
zero bindings, which is exactly why every lookup returned nothing.
`list_distinct_groups()` (`GET /groups`) is unaffected: only
`RULE_BINDING` items use the `sk` prefix `"GROUP#"` — `RULE_PROFILE`/
`PARAMETER_DEF` don't collide there.

**Fix (`api/src/common/dynamodb.py`):** `list_distinct_rule_ids()` now
also checks `sk.startswith("GROUP#") and "#BINDING#" in sk` before
counting a `pk` as a bound rule — matching the exact `sk` shape
`_sk()` produces for real `RULE_BINDING` items. Catalog-only
`RULE_PROFILE`/`PARAMETER_DEF` items sharing the same `pk` are now
correctly excluded.

**Validation performed:** added
`test_list_rule_ids_excludes_catalog_only_rules` to
`api/tests/test_list_ids.py` — plants a real binding for one rule plus
`RULE_PROFILE`/`PARAMETER_DEF` items (mimicking the real loader's
output) for other rules sharing the same `pk` prefix, and asserts only
the genuinely-bound rule comes back. Confirmed this test fails against
the pre-fix code (the catalog-only rule leaks into the result) and
passes after the fix. Full suite: `python -m pytest api/tests/` — 16/16
passed (was 15 before this test was added). `npm run build`
(`tsc --noEmit` + `vite build`) — succeeds cleanly; no UI code changed
for this fix, only the backend candidate list.

### §12.11 — Feature: hybrid catalog visibility for the rule picker (2026-08-02)

**Context:** with §11's loader seeding the full AWS Config rule catalog
(802 `RULE_PROFILE` items, 670 `PARAMETER_DEF` items) into the same table
as `RULE_BINDING`, the UI had all the data it needed to let a user browse
*every* known rule — not just ones someone had already bound — but
`GET /rules` (post-§12.10 fix) only ever returned bound rule IDs, and the
create-binding rule field was a bare free-text input with no
autocomplete. The user's fully-specified request: make the whole rule
catalog visible and searchable from the Bindings screen, with a way to
inspect a rule's parameter definitions before binding it.

**Approach — the user explicitly chose the hybrid of BOTH candidate
options** rather than picking one:

1. Wire the merged rule list into the Create Binding rule picker
   (autocomplete/suggestions), **and**
2. Add a single merged `GET /rules` endpoint carrying a `has_binding`
   flag per rule, so the existing search screen can show catalog-only
   rules too, not just bound ones.

This is a deliberate reversal of the narrower design implied by §12.10's
fix (which only restored `GET /rules` to bound-rules-only): the catalog
is now the candidate source, and bindings are a per-rule status flag on
top of it, not the other way around.

**Search-field and match-style decisions (rule search only):**
- Search field: **"Just rule_id"** — no fuzzy matching against
  description, severity, or parameter names for this feature.
- Match style: **"substring only"** — this explicitly **supersedes the
  earlier fuzzy-matching requirement, for rule search only**. Group
  search's typo-tolerant Levenshtein-prefix matcher (`fuzzyMatches` /
  `fuzzyFilter` in `ui/src/fuzzyMatch.ts`) is unchanged and still backs
  the "By group" search mode. Rule search now uses a new
  `substringMatches` / `substringFilter` pair in the same file: lowercase,
  separator-normalize, then a plain `includes()` check against `rule_id`.

**Result detail level:** drilling into a rule shows its **full
`PARAMETER_DEF` set** — names, types, required/default — **plus scope**,
via a new `GET /rules/{ruleId}/catalog` endpoint, before the user commits
to creating a binding for it.

**Volume handling:** **"default to client side"** — the unbound-rules list
from a rule search is rendered in full with no picker/fan-out gating
(unlike the existing `MAX_FANOUT` picker, which still applies, unchanged,
to *bound* rule matches and to group search, since those trigger real
per-candidate Lambda invocations). Showing every unbound match costs
nothing extra since no lookup is fired for them.

**Terraform/deploy impact:** accepted with no objection — this feature
requires a new API Gateway route and a live `terraform apply` before it
works end-to-end (see "Not yet live" below).

**Backend (`api/`):**
- `api/src/common/dynamodb.py`: replaced `list_distinct_rule_ids()` with
  `list_all_rules_with_binding_status()` — scans the table, unions every
  `PROFILE#<ruleId>` catalog entry with every genuinely-bound rule ID (the
  same `sk.startswith("GROUP#") and "#BINDING#" in sk` check from §12.10),
  and returns `[{rule_id, has_binding}]` sorted by `rule_id`. Added
  `get_rule_catalog(rule_id)`: `GetItem` on `PROFILE#<rule_id>` (raises
  `NotFoundError` → 404 if missing, e.g. for a binding-only rule with no
  seeded catalog entry), plus a `Query` on the `PARAMDEF#` sk prefix under
  the same `pk`, returned as one merged dict (`rule_id, source_identifier,
  description, severity, scopes, managed_rule, parameters`).
  `list_distinct_groups()` is untouched — group search keeps its existing
  bound-only semantics.
- `api/src/rules/list_ids.py`: rewritten to call
  `list_all_rules_with_binding_status()`. **Response shape is a breaking
  change**, intentional per the hybrid decision: `GET /rules` went from
  `list[str]` (bound rule IDs only) to `list[{"rule_id": str,
  "has_binding": bool}]` (every catalog rule).
- `api/src/rules/get_catalog.py`: new handler backing
  `GET /rules/{ruleId}/catalog`.
- `api/src/handler.py`: added the new route
  `("GET", "/rules/{ruleId}/catalog"): get_catalog.handle`.
- `api/tests/test_list_ids.py`: first test updated for the new dict shape;
  the §12.10 catalog-exclusion test was rewritten as
  `test_list_rule_ids_merges_catalog_and_bindings`, now asserting the
  *opposite* of what §12.10 asserted — catalog-only rules and bound rules
  must **both** appear, correctly tagged, with no `PARAMETER_DEF` items
  leaking into the result.
- `api/tests/test_get_catalog.py`: new — covers a happy-path fetch
  (`test_get_catalog_returns_profile_and_parameters`) and the 404 case for
  a rule with a binding but no catalog entry
  (`test_get_catalog_404s_for_binding_only_rule`).
- `crud_api_iam.tf`: comment near the DynamoDB IAM policy statement
  updated — it referenced the now-removed `list_distinct_rule_ids`; now
  points at `list_all_rules_with_binding_status` and notes the new
  catalog endpoint needs no additional IAM grant (existing
  GetItem/Query/Scan permissions already cover it).

**Terraform (`crud_api_gateway.tf`):** added a new
`/rules/{ruleId}/catalog` resource/method/integration/OPTIONS-CORS block,
following the exact pattern already used for `rule_bindings`. Added the
new resource/method/integration IDs to both
`aws_api_gateway_deployment.rule_catalog_api`'s `triggers.redeployment`
sha1 list and its `depends_on` list — easy to forget, and forgetting it
means the route exists in the config but never actually deploys to the
live stage.

**Frontend (`ui/`):**
- `ui/src/api/bindingsApi.ts`: `listAllRuleIds()` return type changed to
  `RuleWithBindingStatus[]` (`{rule_id, has_binding}[]`), matching the new
  `GET /rules` shape. Added `RuleCatalog` / `RuleCatalogParameter` types
  and `getRuleCatalog(ruleId)` hitting `GET /rules/{ruleId}/catalog`.
- `ui/src/fuzzyMatch.ts`: added `substringMatches` / `substringFilter`
  alongside the existing `fuzzyMatches` / `fuzzyFilter` — the latter pair
  is untouched and still used for group search.
- `ui/src/pages/BindingsBrowser.tsx`: rule-mode search now calls the
  merged `GET /rules`, substring-matches the query against `rule_id`, and
  splits matches into **bound** (fanned out to `listBindingsForRule`
  exactly like before, feeding the same results table, with the same
  `MAX_FANOUT` too-broad picker) and **unbound** (rendered as a standalone
  table with "View details" and "Create binding" buttons per row — no
  fan-out, shown in full per the client-side volume decision). "View
  details" (available for both bound and unbound rule matches) calls
  `getRuleCatalog` and renders description, severity, scopes,
  managed-rule flag, and the full parameter table inline. "Create
  binding" from an unbound row opens the existing `BindingForm` in create
  mode pre-filled with that `rule_id` via a new `pendingCreateRuleId`
  piece of state. Group search's fuzzy-match behavior, its own
  `groupMatches`/`groupTooBroad` state, and its picker/fan-out are
  unchanged from §12.9/§12.10's fixed version — the two search modes now
  fully own separate state.
- `ui/src/components/BindingForm.tsx`: create-mode Rule ID field is now
  an `<input list="rule-id-options">` backed by a `<datalist>` populated
  from `listAllRuleIds()` on mount (best-effort — a fetch failure just
  leaves the field a plain text input, it never blocks manual entry).
  Edit mode is unaffected since its rule ID field is fixed/disabled.

**Validation performed:** `python -m pytest api/tests/` — **18 passed**
(16 baseline + the 2 new `test_get_catalog.py` tests; the rewritten
`test_list_ids.py` test also passes). Terraform: temporarily stripped the
`cloud{}` block from `terraform.tf` (backed up first), ran
`terraform init -backend=false -input=false && terraform validate` →
"Success! The configuration is valid.", then restored `terraform.tf` from
the backup and confirmed the `cloud{}` block was back. Frontend:
`npm run build` (`tsc --noEmit` + `vite build`) — succeeds cleanly, no
type errors.

**Not yet live:** exactly like every other backend/Terraform change in
this document, this needs a real `terraform apply` in TFC workspace
`Y62DB` before `GET /rules`'s new response shape or the new
`GET /rules/{ruleId}/catalog` route actually exist against the deployed
API — validation above only proves the HCL is syntactically valid and the
Python logic is correct in isolation. Once applied, re-verify live with
the same Cognito-auth `curl` pattern used for prior fixes (get an ID
token via `InitiateAuth` for the `testuser` test user, then call
`GET {api_base_url}/rules` and `GET {api_base_url}/rules/<a-real-rule-id>/catalog`
with it as the `Authorization` header) before considering this feature
verified end-to-end.

### §12.12 — Feature: AWS Amplify Hosting CI/CD for ui/ (2026-08-03)

**Context:** `ui/` (the bindings CRUD frontend) has only ever been run
locally via `npm run dev` / `npm run build`. This section adds continuous
deployment so pushes to `main` automatically build and publish the app,
closing the last item on the original v1 roadmap.

**Decisions (user's own words / explicit choices):**
1. Management — "Terraform-managed" (not console-managed). Amplify's
   `aws_amplify_app`/`aws_amplify_branch` resources are added to this
   repo's existing root Terraform, consistent with every other resource
   in the stack.
2. Domain — "Default amplifyapp.com subdomain." No custom domain/Route 53
   work in this pass.
3. Branch scope — "main only." No PR preview branches, no
   `enable_auto_branch_creation`.

**Terraform changes:**
- `amplify_variables.tf` (new): `github_repository_url` (default
  `https://github.com/rtrivgreg/Y62DB`), `github_access_token`
  (sensitive, no default — must be set directly as a sensitive variable
  in the Terraform Cloud workspace UI, never in `terraform.tfvars` or
  committed anywhere), `amplify_app_name` (default
  `y62db-bindings-ui`).
- `amplify_hosting.tf` (new): `aws_amplify_app.bindings_ui` (platform
  `WEB`, `repository`/`access_token` wired to the GitHub repo, one
  `custom_rule` for SPA-style `404-200` → `/index.html` fallback — a
  no-op today since `ui/` has no client-side router yet, but avoids a
  broken-deep-link surprise the moment one is added) and
  `aws_amplify_branch.main` (`branch_name = "main"`, `stage =
  "PRODUCTION"`, `framework = "React"`, `enable_auto_build = true`).
  `build_spec` is intentionally left unset on both resources — Amplify
  auto-detects the checked-in `amplify.yml` at the repo root instead of
  needing the build spec embedded as a Terraform string.
- `amplify_outputs.tf` (new): `amplify_app_id`, `amplify_default_domain`,
  `amplify_main_branch_url` (constructed as
  `https://main.<default_domain>`).
- `amplify.yml` (new, repo root): Amplify's monorepo "applications"
  build-spec format with `appRoot: ui`, since the frontend lives in a
  subdirectory, not the repo root. Build phases: `npm ci` → `npm run
  build`, artifacts from `ui/dist`, `node_modules` cached between builds.
  No environment variables are needed in the build — `ui/src/amplify-config.ts`
  hardcodes the Cognito/API identifiers already, it doesn't read
  `import.meta.env`/`VITE_*` vars.

**Known external dependency (cannot be resolved from inside this repo):**
the IAM role/policy that Terraform Cloud's AWS OIDC integration assumes
for this workspace must include `amplify:*` permissions (at minimum
`CreateApp`, `CreateBranch`, `UpdateApp`, `GetApp`, `GetBranch`,
`TagResource`, `CreateWebhook`). That role isn't defined anywhere in this
repo — if `terraform apply` fails with `AccessDenied` on any `amplify:*`
action, the role's policy needs to be widened out-of-band, wherever it's
actually managed.

**Validation performed:** verified the exact `aws_amplify_app` /
`aws_amplify_branch` argument schemas against the current
`hashicorp/aws` provider docs before writing any HCL (platform values,
`custom_rule` block shape, `access_token` vs `oauth_token`, valid `stage`
values) to avoid guessing field names. Terraform: temporarily stripped
the `cloud{}` block from `terraform.tf` (backed up first, brace-depth
technique per §12.11), ran `terraform init -backend=false -input=false
&& terraform validate` → "Success! The configuration is valid.", then
restored `terraform.tf` from the backup and confirmed via diff that it
matched the original exactly. `pytest`/`npm run build` were not re-run
since no Python or frontend application code changed in this pass — only
new root-level `.tf` files and a new `amplify.yml`.

**Not yet live — and not yet appliable without one manual step first:**
before `terraform apply` will succeed, a GitHub personal access token
(classic, `repo` scope, or fine-grained with `Contents: Read-only` +
`Webhooks: Read & write` on `rtrivgreg/Y62DB`) must be created and set as
the sensitive `github_access_token` variable directly in the Terraform
Cloud workspace UI (org `RSHL2136`, workspace `Y62DB`). This was
deliberately never handled by the agent or passed through chat — Amplify
only needs the token once, at app-creation time, to install its own
deploy key and webhook. After that variable is set and `terraform apply`
succeeds, the live URL will be `amplify_main_branch_url` from the new
outputs (`https://main.<app-id>.amplifyapp.com` in practice) — verify by
opening it in a browser and confirming the Cognito sign-in screen
renders, then re-push to `main` once and confirm Amplify's build history
shows a new successful build.

**Applied and live (2026-08-03):** `terraform apply` succeeded in TFC
after `github_access_token` was set as a sensitive workspace variable.
Live identifiers: `amplify_app_id = d1i2kpf4n8z1da`,
`amplify_default_domain = d1i2kpf4n8z1da.amplifyapp.com`,
`amplify_main_branch_url = https://main.d1i2kpf4n8z1da.amplifyapp.com`.
As expected, app creation alone did not trigger a build (the push that
created this app predated the webhook's existence) — confirmed via a
direct request to the URL, which served Amplify's default "Welcome...
your app will appear here once you complete your first deployment"
placeholder rather than the real app. This commit is the first push
made *after* the webhook exists, and is expected to trigger the first
real build automatically.

**Confirmed live (2026-08-03):** after that push, `https://main.d1i2kpf4n8z1da.amplifyapp.com`
now serves the real built app (verified title + JS/CSS bundle assets all
returning HTTP 200), not the placeholder. Amplify Hosting CI/CD for
`ui/` is complete — every future push to `main` auto-builds and
auto-deploys.

### §12.13 — Feature: Textual TUI client for the bindings CRUD API (2026-08-06)

**Context:** user asked for a second, terminal-based way to run this
application — a TUI that performs CRUD against the same live API `ui/`
talks to, built with the Textual Python library, using Textual's default
widgets/behavior (mouse support included) rather than custom low-level
terminal handling.

**Scope decision (explicit, via `ask_user_question`):** "Core CRUD only"
— search (rule ID substring match / group fuzzy match), create, edit,
delete, matching `ui/src/pages/BindingsBrowser.tsx` and
`ui/src/components/BindingForm.tsx` behavior and error wording as
closely as possible. Deliberately **excluded** from v1 (the user's other
option): the read-only rule-catalog drill-in ("View details" on unbound
rules) and the too-many-matches picker / batched fan-out — this TUI fans
out to every search match directly, which is fine at this project's
current data scale.

**New component — `tui/` (new top-level folder, sibling to `ui/` and
`api/`):**
- `config.py` — live AWS identifiers (Cognito App Client ID, API base
  URL), kept in lockstep with `ui/src/amplify-config.ts`. No new AWS
  resources — this is a second client against the *existing* backend.
- `auth.py` — Cognito `InitiateAuth` (`USER_PASSWORD_AUTH` flow) via
  `boto3`. No AWS IAM credentials needed to run the TUI: Cognito's
  end-user auth operations are unsigned/unauthenticated at the SDK
  level, confirmed empirically (see Validation below) — same reason the
  web UI's Authenticator component needs no IAM creds either.
- `fuzzy_match.py` — direct Python port of `ui/src/fuzzyMatch.ts`
  (Levenshtein-based typo-tolerant prefix match for groups, plain
  substring match for rule IDs), so both search modes match the same
  things the web UI's search box does.
- `api_client.py` — direct async port of `ui/src/api/bindingsApi.ts`
  (`BindingsApiClient`, `Binding`, `BindingsApiError`) — same endpoints,
  same envelope-unwrapping, same error codes/status surfaced to the
  caller.
- `app.py` — the Textual `App` plus four screens: `LoginScreen`
  (Cognito sign-in), `BrowseScreen` (search mode select + query input +
  `DataTable` results + Edit/Delete-selected buttons + New
  binding/Sign out), `BindingFormScreen` (shared create/edit modal — same
  validation as the web form: extra-payload JSON must parse to an
  object, rule ID + group required, version auto-incremented on edit and
  sent as `expected_version` for optimistic locking), and
  `ConfirmDeleteScreen` (stock Textual `ModalScreen` yes/no dialog — the
  same pattern shown in Textual's own docs/examples for confirmation
  dialogs).
- `requirements.txt` (`textual`, `httpx`, `boto3`), `README.md` (setup/run
  instructions, mouse-support notes incl. the `tmux` `set -g mouse on`
  caveat), `tests/` (see Validation).

**Mouse support:** no custom code needed — Textual enables mouse
reporting by default in any terminal that supports xterm mouse tracking
(iTerm2, Terminal.app, Windows Terminal, most Linux terminals). Clicking
`DataTable` rows, buttons, and `Select` dropdowns all work out of the
box; only `tmux` needs `set -g mouse on` added by the user first.

**Notable side benefit over the web UI:** the web UI's Delete
confirmation uses the browser's native `window.confirm()` — which, per
the manual-QA session on 2026-08-03/2026-08-06, turned out to reliably
hang this project's own browser-automation tooling (native
browser-chrome-level dialogs sit outside the page DOM). `ConfirmDeleteScreen`
here is a normal in-app Textual screen instead, not a terminal-chrome
popup — no equivalent automation hazard.

**Validation performed:**
- `pip install -r tui/requirements.txt` (+ `pytest`, `pytest-asyncio`)
  into a fresh `tui/.venv` — clean install, `textual==0.89.1`,
  `httpx==0.28.1`, `boto3==1.43.66`.
- `python -m py_compile` on all five modules — clean.
- `tui/tests/test_fuzzy_match.py` (13 cases) — ports the exact examples
  documented in `ui/src/fuzzyMatch.ts`'s own docstring (exact match,
  separator normalization, shorter-candidate rejection, prefix
  extension, typo tolerance, the short-query guardrail, substring mode's
  lack of typo tolerance) — all pass.
- `tui/tests/test_app_boots.py` — headless smoke test via Textual's own
  `App.run_test()`/`Pilot` utilities: app mounts to `LoginScreen`
  without crashing; submitting the sign-in form with both fields empty
  shows the client-side "required" error with no network call attempted
  — both pass.
- `tui/pytest.ini` sets `asyncio_mode = auto` so plain `pytest` (run from
  `tui/`) picks up both async tests with no extra flags — confirmed:
  "14 passed".
- **Live end-to-end check against the real API** (`tui/tests/live_check.py`,
  a manual script, not part of the automated suite since it needs real
  Cognito credentials): signed in as `testuser` via `auth.sign_in`
  (boto3 `InitiateAuth`, no AWS IAM credentials configured in this
  sandbox — confirming Cognito's user-auth operations really are
  unsigned), then exercised the exact `BindingsApiClient` methods the
  TUI screens call — create → list → optimistic-lock update (v1→v2) →
  confirmed a stale-version update correctly raises `BindingsApiError`
  with `code="conflict"` (HTTP 409) → delete → confirmed gone. Output:
  "ALL LIVE CHECKS PASSED". Self-cleaning — the test binding
  (`ui-test-rule`/`ui-test-group`/`tui-livecheck`) no longer exists in
  the live table afterward.
- Full interactive mouse-driven use of the running TUI (as opposed to
  the headless boot/API checks above) was not exercised live in this
  session — the terminal-rendering/mouse-click path itself should be
  spot-checked by the user on their own machine.

**Follow-up amendment (same day, 2026-08-06): catalog search added back
in a minimal form.** After first use, the user searched for "s3" and
"sage" in "By rule ID" mode and got confused by empty/sparse results.
Root cause (not a bug): the Bindings browser — in both the TUI and the
original `BindingsBrowser.tsx` — only ever fans out to rules/groups that
**already have a binding**. Live data at the time: out of 810 catalog
rules, only 2 have any binding at all (`cloudfront-s3-origin-access-control-enabled`
plus the `ui-test-rule` fixtures); all 24 `sagemaker-*` rules and the
other 38 `s3`-containing catalog rules have none. Only 7 groups exist
total (`a2_g`, `a3`, `a4`, `c2`, `corp`, `smoke-test`, `ui-test-group`).
Confirmed live that the search logic itself was already correct —
searching "s3" does return the one bound match.

Given this, the user asked to add catalog search back (reversing part
of the original §12.13 "core CRUD only" scope decision) so unbound
catalog rules can be found and bound directly from the TUI, without the
full "View details" catalog drill-in that was still intentionally left
out (severity/description/scope metadata display is a separate,
un-requested feature).

**Implementation:** `BrowseScreen` in rule-ID mode now splits
substring matches into two groups — bound rule IDs (fanned out to their
bindings as before, shown in the existing results table) and unbound
rule IDs (shown in a new, separate `catalog_table` labeled "Catalog
rules matching your search with no binding yet"). A new "Create binding
for selected" button opens the same `BindingFormScreen` create modal,
pre-filled with the selected catalog rule ID. Group-mode search is
unchanged — groups aren't a catalog concept (they're just labels that
exist on bindings), so there's nothing unbound to show there.

**Validation:**
- `tui/tests/test_catalog_search.py` (3 new headless tests, fake API
  client, no live calls): confirms a mixed "s3" search splits correctly
  into 1 bound result + 2 unbound catalog matches; confirms a "sage"-style
  search with zero bound matches still surfaces the 1 unbound catalog
  match; confirms selecting a catalog row enables the "Create binding for
  selected" button. Full suite now "17 passed".
- Live check: searched real data for "sage" (24 unbound catalog
  matches confirmed), created a binding for `sagemaker-app-image-config-tagged`
  via the same code path the button triggers, confirmed `has_binding`
  flipped to `true` afterward, then deleted it — self-cleaning, no
  leftover data.
