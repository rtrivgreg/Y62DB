# Y62DB Project Resumption Blueprint

**Document purpose:** disaster recovery. If all session history, chat memory, and working context for this initiative were lost, this single document is intended to be sufficient — on its own — to understand what Y62DB is, what has been built, what is live in AWS today, what remains, and exactly how to safely pick the work back up.

**Snapshot date:** 2026-08-02 (America/New_York evening) — reflects the repository at commit `7e4c701` on `rtrivgreg/Y62DB`, `main` branch, with all changes through Blueprint §12.11 applied and independently verified live against the deployed API in this session.

---

## Page 1 — Executive Summary

### What this is

Y62DB is the catalog and control-plane data layer for curated AWS Config managed-rule metadata, parameter definitions, and organization-specific rule "bindings" (per-group parameter overrides/activation state). This initiative adds a CRUD API and a browser-based UI on top of that data so a non-technical user can manage rule bindings without hand-editing DynamoDB, plus browse the full AWS Config managed-rule catalog and its parameter definitions before creating a binding.

### Technology & AWS service inventory

| Layer | Technology / Service |
|---|---|
| Infrastructure as Code | Terraform (HCL), Terraform Cloud remote backend |
| Compute | AWS Lambda (Python 3.12, 256 MB, 10s timeout) — one function serving all API routes |
| API layer | Amazon API Gateway (REST API, `AWS_PROXY` integration, per-route CORS via `MOCK` OPTIONS) |
| Data store | Amazon DynamoDB — one single-table design (`y62db-config-rule-catalog`) with a GSI (`gsi1-group-bindings`); plus two legacy, permanently-retained tables (`config_rules`, `config_rule_parameters`) owned by an unrelated application |
| Auth / Identity | Amazon Cognito (User Pool + public app client, SRP + refresh-token flows) fronting an API Gateway `COGNITO_USER_POOLS` authorizer |
| Observability | Amazon CloudWatch Logs (Lambda log group, managed retention) |
| Frontend | React 18 + TypeScript + Vite 5, `aws-amplify` / `@aws-amplify/ui-react` (`<Authenticator>` component; plain `fetch()` for API calls, not Amplify's REST category, because the Cognito ID token must be passed directly) |
| Backend language/tooling | Python 3.12, `boto3`, `pytest` + `moto` (mocked DynamoDB for tests, no AWS account needed to run the suite) |
| Frontend tooling | TypeScript, Vite, `tsc --noEmit` for type-checking |
| Data ingestion | Python loader (`loader/loader.py`) using `python-hcl2` to parse AWS managed-rule Terraform metadata from a separate private repo (`config-rules-all`) and bulk-write it into DynamoDB |
| Version control / CI | Git, GitHub (`rtrivgreg/Y62DB`) |
| Planned, not yet built | AWS Amplify Hosting (CI/CD for the `ui/` frontend) |

### Architectural outline

```
                         ┌─────────────────────────┐
   Browser (React/Vite)  │  <Authenticator> (Amplify UI)
   ui/ (not yet on        │  fetch() with Cognito ID token
   Amplify Hosting)       └───────────┬─────────────┘
                                       │ HTTPS + Authorization: <IdToken>
                                       ▼
                         ┌─────────────────────────┐
                         │  Amazon Cognito          │
                         │  User Pool +             │
                         │  COGNITO_USER_POOLS      │
                         │  API Gateway authorizer  │
                         └───────────┬─────────────┘
                                     ▼
                         ┌─────────────────────────┐
                         │  API Gateway (REST)      │
                         │  /rules/{ruleId}/bindings│
                         │  /rules/{ruleId}/catalog │
                         │  /groups/{group}/bindings│
                         │  /rules  /groups         │
                         └───────────┬─────────────┘
                                     ▼  AWS_PROXY
                         ┌─────────────────────────┐
                         │  Lambda: crud_api        │
                         │  (single function,       │
                         │  routes on method+path)  │
                         └───────────┬─────────────┘
                                     ▼ boto3 (GetItem/PutItem/Query/Scan)
                         ┌─────────────────────────┐
                         │  DynamoDB                │
                         │  y62db-config-rule-catalog│
                         │  (RULE_PROFILE,           │
                         │   PARAMETER_DEF,          │
                         │   RULE_BINDING items;     │
                         │   gsi1-group-bindings)    │
                         └─────────────────────────┘

  (Separate, untouched, permanently retained — owned by another app):
  DynamoDB: config_rules (801 items), config_rule_parameters (669 items)
```

Terraform manages every box above except the DynamoDB table itself (deliberately referenced via a read-only `data` source, never a `resource`, because it predates and lives outside this stack's Terraform Cloud state — see §4 below).

### Completed items

- [x] Bindings CRUD API — full `RULE_BINDING` create/read/update(optimistic-locked)/delete/list-by-rule/list-by-group, live and verified end-to-end with a real Cognito bearer token.
- [x] Least-privilege Lambda IAM policy scoped to exactly the one table + GSI (+ `Scan` added later for catalog/search features).
- [x] Cognito authentication applied to all data-touching routes; unauthenticated/garbage-token requests confirmed rejected with `401`; `OPTIONS` preflight confirmed unauthenticated.
- [x] Data migration: `loader/loader.py` rewritten for the single-table schema and run for real, seeding 802 `RULE_PROFILE` + 670 `PARAMETER_DEF` items into `y62db-config-rule-catalog` — independently verified via direct DynamoDB scans/queries.
- [x] Legacy tables (`config_rules`, `config_rule_parameters`) confirmed untouched and explicitly documented as permanently retained (owned by an unrelated Python application — **do not archive, delete, or modify**).
- [x] Frontend scaffolded (Vite + React + TS), wired to real Cognito auth and the real API Gateway base URL, verified from an actual signed-in browser session.
- [x] Full bindings CRUD forms (create/edit/delete) built on top of the search/list screen.
- [x] Typo-tolerant fuzzy search (rule ID / group) plus five follow-on bug fixes (short-query over-matching, fragile fan-out, broad-match dead-end error, Lambda concurrency-quota protection, stale async response race) — all applied to live AWS and validated.
- [x] Fix for `GET /rules` leaking catalog-only rules with zero bindings.
- [x] **Hybrid catalog-visibility feature (§12.11)** — merged `GET /rules` (every catalog rule tagged `has_binding`), new `GET /rules/{ruleId}/catalog` (full parameter definitions + description/severity/scope), substring rule search, unbound-rule browsing, Rule ID autocomplete on the create form, and a parameter drill-in panel. **Applied via `terraform apply` and independently re-verified live in this session** with real Cognito-authenticated `curl` calls against both endpoints (see §7).
- [x] All backend changes validated with `pytest` (18/18 passing) at every step; all Terraform changes validated with `terraform validate` (brace-depth-counting technique for temporarily stripping the `cloud{}` block — see §6); all frontend changes validated with `npm run build` (`tsc --noEmit` + `vite build`).

### Outstanding items

- [ ] **Amplify Hosting CI/CD** — connect the `ui/` app to a git branch for automated builds/deploys (currently run only via local `npm run dev`/`npm run build`). This is the next unstarted roadmap step.
- [ ] **Amplify app Terraform-management decision** — not yet decided whether `aws_amplify_app`/`aws_amplify_branch` should be Terraform-managed or left to Amplify's own console/CLI.
- [ ] **Manual QA test battery** (`ui/TEST_PLAN.md`) — Read/Search (R1–R5) and Create (C1–C8) and Update happy-path/lock/JSON cases (U1–U4) have passed; **U5 (stale-version conflict across two tabs), U6 (invalid JSON on edit), all of Delete (D1–D4), all of Auth/session (A1–A3), all of Resilience (X1–X3), and final Cleanup** are still pending.
- [ ] **`terraform/` subfolder reconciliation** — a second, single-table Terraform design exists in the repo but was applied once by hand and is **not** under Terraform Cloud state management; deliberately deferred as a bigger, riskier future project (e.g. via `terraform import`), not urgent.
- [ ] A dedicated, standalone "browse the full 802-rule catalog" list view does not exist yet — today a user can only inspect a rule's catalog entry by searching for it and clicking "View details" (§12.11). Functionally close to the originally-scoped read-only browser, but not a paginated full-catalog listing page.

### Percent completion

| Workstream | Status | Estimate |
|---|---|---|
| Backend CRUD API (bindings) | Live, verified | 100% |
| DynamoDB data model & data migration | Live, verified | 100% |
| Cognito authentication | Live, verified | 100% |
| Frontend scaffold + Auth integration | Live, verified | 100% |
| Frontend CRUD forms | Built & applied; search interactively verified, create/edit/delete not all interactively browser-tested | ~90% |
| Search UX + bug-fix chain (§12.5–§12.10) | Live, verified | 100% |
| Hybrid catalog visibility (§12.11) | Live, verified this session | 100% |
| Manual QA test battery | 17 of 29 listed test cases passed | ~59% |
| Amplify Hosting CI/CD | Not started | 0% |
| `terraform/` subfolder reconciliation | Deliberately deferred (backlog, out of current scope) | N/A |

**Overall: roughly 90% complete against the originally-scoped v1 roadmap** (Cognito-secured bindings CRUD + rule/parameter catalog browsing, deployed and functioning end-to-end). The remaining ~10% is CI/CD wiring for hosting and finishing the manual QA pass — no known backend or data-model work remains.

---

## 2. Data Model (authoritative source: `schemas/access-patterns.md`)

Single-table design in `y62db-config-rule-catalog`:

| Entity | pk | sk | Notes |
|---|---|---|---|
| `RULE_PROFILE` | `RULE#<rule_id>` | `PROFILE#<rule_id>` | Canonical AWS managed-rule record (802 items, seeded) |
| `PARAMETER_DEF` | `RULE#<rule_id>` | `PARAMDEF#<parameter_name>` | Known parameter metadata (670 items across 412 rules, seeded) |
| `SCOPE_DEF` | `RULE#<rule_id>` | `SCOPEDEF#<scope_name>` | Deliberately deferred — scope data currently lives as a `scopes` attribute on `RULE_PROFILE` instead |
| `RULE_BINDING` | `RULE#<rule_id>` | `GROUP#<group_id>#BINDING#<binding_id>` | **The only entity type the CRUD API manages.** `gsi1pk=GROUP#<group_id>`, `gsi1sk=RULE#<rule_id>#BINDING#<binding_id>` |
| `ORG_GROUP` | `GROUP#<group_id>` | `PROFILE#<group_id>` | Internal group metadata — not built out |
| `AUDIT_EVENT` | `RULE#<rule_id>` | `AUDIT#<timestamp>#<event_id>` | Immutable change history — not built out |

Confirmed explicit scope decision from the repo owner: "crud-enable Y62DB" means CRUD on `RULE_BINDING` only. Rule profiles, parameter definitions, scope definitions, groups, and audit events are read-only or entirely out of scope for the API.

---

## 3. API Surface (canonical contract: `api/README.md`)

Single Lambda (`crud_api`) behind one REST API:

```
GET    /rules/{ruleId}/bindings                    list every group a rule is bound to
POST   /rules/{ruleId}/bindings                     create a binding (409 if it already exists)
GET    /rules/{ruleId}/bindings/{group}/{binding}   read one binding
PUT    /rules/{ruleId}/bindings/{group}/{binding}   full replace, optimistic-locked via expected_version
DELETE /rules/{ruleId}/bindings/{group}/{binding}   remove a binding
GET    /groups/{group}/bindings                     list every rule bound to a group (via gsi1)
GET    /rules                                       every catalog rule, tagged {rule_id, has_binding} (§12.11)
GET    /rules/{ruleId}/catalog                      full RULE_PROFILE + PARAMETER_DEF set for one rule (§12.11)
GET    /groups                                      sorted distinct groups that have at least one binding (§12.5)
```

All routes also expose an `OPTIONS` method (unauthenticated `MOCK` integration) for CORS. Response envelope:

```json
// success
{ "success": true, "data": { ... }, "error": null, "meta": { "request_id": "...", "timestamp": "..." } }
// error
{ "success": false, "data": null, "error": { "code": "not_found", "message": "...", "details": {...} }, "meta": {...} }
```

Status codes: `200` read/update, `201` created, `204` deleted, `400` validation, `401` unauthenticated, `404` not found/unknown route, `409` conflict (duplicate create, or stale `expected_version`), `500` unhandled.

All routes except `OPTIONS` require `Authorization: <Cognito ID token>` (not the access token — the authorizer checks the `aud` claim, which only the ID token carries in this no-OAuth-scopes setup).

---

## 4. Infrastructure Design Decisions Worth Remembering

- **The real DynamoDB table is a `data` source in Terraform, never a `resource`.** It predates this CRUD stack and isn't in any Terraform Cloud state; managing it as a `resource` here would either fail on name collision or silently adopt/orphan production data. IAM policies reference its ARN via `data.aws_dynamodb_table.rule_catalog.arn`.
- **Two Terraform designs coexist in this repo on purpose, not by accident:** the root module (legacy two-table design, the only one actually under Terraform Cloud management) and a `terraform/` subfolder (single-table redesign, applied once by hand, not under any remote state). They are not competing implementations — the root's legacy tables are stale/orphaned catalog data owned by a separate app, while the real, seeded, in-use table lives outside Terraform's tracked resources entirely. See "Outstanding items" for the deferred reconciliation.
- **Optimistic locking on `PUT`** is a genuine DynamoDB `ConditionExpression` (`attribute_exists(pk) AND payload.version = :expected_version`), not a read-then-write race — a `ConditionalCheckFailedException` maps to a `409`.
- **Cognito was chosen deliberately** so the same identity source serves both the API Gateway authorizer and the future Amplify frontend's Auth category — one user pool, two consumers.
- **Fuzzy vs. substring search are intentionally different per search mode.** Group search still uses Levenshtein-prefix fuzzy matching (`fuzzyMatches`/`fuzzyFilter`, unchanged since §12.5–§12.10). Rule search was deliberately changed to substring-only matching against `rule_id` in §12.11, per explicit user decision — this supersedes fuzzy matching *for rule search only*.
- **Client-side volume handling for the unbound-rules list** — rendered in full with no fan-out gating, because no per-item Lambda invocation is triggered for unbound rules (unlike the `MAX_FANOUT=40` picker + `FANOUT_BATCH_SIZE=6` batching that still protects real per-candidate lookups for bound rules and groups, added specifically after a real AWS Lambda concurrency-quota incident — see §12.8 in the full history below).

---

## 5. Infrastructure & Access Identifiers (carry-forward reference)

| Item | Value |
|---|---|
| GitHub repo | `rtrivgreg/Y62DB` |
| Current commit (main, this snapshot) | `7e4c701` |
| Local clone path (in this sandbox) | `/home/user/workspace/Y62DB` |
| Terraform Cloud org | `RSHL2136` |
| Terraform Cloud workspace | `Y62DB` |
| AWS account | `418295699841` |
| AWS region | `us-east-1` |
| Real DynamoDB table | `y62db-config-rule-catalog` |
| GSI name | `gsi1-group-bindings` |
| Legacy DynamoDB tables (permanently retained, do not touch) | `config_rules` (801 items), `config_rule_parameters` (669 items) |
| API base URL | `https://3lkxt728eh.execute-api.us-east-1.amazonaws.com/dev` |
| Lambda function name | `y62db-rule-catalog-api-dev` |
| Cognito User Pool ID | `us-east-1_5OUP1L4hf` |
| Cognito App Client ID | `2eruh11a9kc2lbdd286q282ofb` |
| Test Cognito user | `testuser` / `BeSeeingYou25!` |

### Live re-verification pattern (no Terraform Cloud connector / browser session needed)

```bash
# 1. Get a real ID token
curl -s -X POST https://cognito-idp.us-east-1.amazonaws.com/ \
  -H 'Content-Type: application/x-amz-json-1.1' \
  -H 'X-Amz-Target: AWSCognitoIdentityProviderService.InitiateAuth' \
  -d '{"AuthFlow":"USER_PASSWORD_AUTH","ClientId":"2eruh11a9kc2lbdd286q282ofb","AuthParameters":{"USERNAME":"testuser","PASSWORD":"BeSeeingYou25!"}}'
# -> take .AuthenticationResult.IdToken

# 2. Call the live API with it as the Authorization header
curl -s -H "Authorization: <IdToken>" "https://3lkxt728eh.execute-api.us-east-1.amazonaws.com/dev/rules"
curl -s -H "Authorization: <IdToken>" "https://3lkxt728eh.execute-api.us-east-1.amazonaws.com/dev/rules/access-keys-rotated/catalog"
```

This exact pattern was used in this session to confirm §12.11 is live: `GET /rules` returns the merged `{rule_id, has_binding}` shape, and `GET /rules/{ruleId}/catalog` returns full parameter definitions for a valid rule and a clean `404 not_found` for an invalid one.

---

## 6. Validation Methodology (repeatable, still correct today)

- **`pytest` in `api/`** — currently 18/18 passing, using `moto` to mock DynamoDB (`conftest.py` builds a table with production's exact `pk`/`sk`/GSI schema). No AWS account needed.
- **`terraform validate`** — the repo's `cloud{}` block requires Terraform Cloud login, unavailable in a plain sandbox. Established, repeatable technique: temporarily strip the `cloud{}` block using a **brace-depth-counting** line-by-line script (not a naive regex — a nested `workspaces{}` block breaks simple regex stripping), run `terraform init -backend=false -input=false && terraform validate`, confirm `Success!`, then restore the original file exactly and confirm via `cat`/diff that it's back.
- **`npm run build`** in `ui/` (`tsc --noEmit && vite build`) — catches type errors and confirms the production bundle builds cleanly.
- **Live re-verification** — the Cognito `curl` pattern in §5 above is the only way to confirm a `terraform apply` actually took effect against the real deployed stage, since there is no Terraform Cloud connector in this environment (all applies must be triggered by the repo owner directly in Terraform Cloud).

---

## 7. Chronological Feature/Fix History (condensed)

1. **Bindings CRUD API built** — Lambda + API Gateway + least-privilege IAM, `data`-sourced DynamoDB table, optimistic locking on `PUT`. Applied to real AWS; confirmed zero diff on legacy tables.
2. **Cognito authentication added and applied** — User Pool + authorizer on all six data-touching routes; live-verified rejecting unauthenticated/garbage-token requests.
3. **Loader rewritten and re-run for the single-table schema** — 802 `RULE_PROFILE` + 670 `PARAMETER_DEF` items seeded into `y62db-config-rule-catalog`, independently verified via direct scans/queries. Legacy tables confirmed untouched and formally marked permanently retained (owned by a separate, unrelated application).
4. **Full CRUD verified live with a real bearer token** — all 8 request/edge-case combinations passed against the deployed endpoint.
5. **`ui/` scaffolded** — Vite + React + TS, real Cognito auth wired via `<Authenticator>`, plain `fetch()` for API calls, verified from an actual signed-in browser session.
6. **Full CRUD forms built** (create/edit/delete) on top of search/list, with optimistic-locking UX (auto-incremented version, distinct 409 messaging) and freeform-JSON payload extras.
7. **Typo-tolerant fuzzy search added** for rule ID / group, backed by two new scan-based list endpoints (`GET /rules`, `GET /groups`).
8. **Five sequential bug fixes**, each found via real manual QA and each applied to live AWS:
   - Short-query over-matching (`a2` matching everything `a`-prefixed) — fixed with a `MIN_FUZZ_LEN` exact-prefix floor.
   - Fragile `Promise.all` fan-out wiping all results on one failure — switched to `Promise.allSettled`.
   - Broad-match (`EC2`/`S3`) dead-end error — replaced with a clickable candidate picker.
   - A real AWS Lambda **Concurrent executions** quota incident (quota was 10, an auto-adjust increase request failed) traced to this fan-out — fixed with batched fan-out (`FANOUT_BATCH_SIZE=6`) and a manual quota increase submitted outside Terraform.
   - Stale async search responses overwriting newer ones — fixed with a search-generation counter guard.
9. **`GET /rules` catalog-leak fix** — a rule-catalog seeding side effect caused catalog-only rules with zero bindings to appear as false-positive search results; fixed by checking the binding-specific `sk` shape, not just the `pk` prefix.
10. **Hybrid catalog-visibility feature (§12.11)** — merged `GET /rules` with a `has_binding` flag, new `GET /rules/{ruleId}/catalog` drill-in endpoint, substring-only rule search, unbound-rule browsing and one-click "Create binding" pre-fill, Rule ID autocomplete. Applied via `terraform apply` and **independently re-verified live in this session.**

For full prose detail, rationale, and code-level specifics behind every item above, the authoritative in-repo document is `docs/BLUEPRINT.md` (currently 1,196 lines, §1–§12.11) — this resumption blueprint summarizes it but does not replace it.

---

## 8. Open Risks & Guardrails

1. **Legacy tables (`config_rules`, `config_rule_parameters`) must never be archived, deleted, or modified.** Confirmed by the repo owner: they are an essential component of a separate, unrelated Python application, not a Y62DB concern. This is documented in `docs/BLUEPRINT.md` §7/§8.3 and in durable agent memory under the category `work.projects.dynamodb_terraform.legacy_tables_preservation`. Treat this as closed and permanent, not a future cleanup candidate.
2. **`terraform/` subfolder is orphaned from Terraform Cloud state.** Standing drift risk — the real table's own definition isn't under any remote state. Deliberately not reconciled yet (e.g. via `terraform import`) because it's a bigger, riskier project than anything done so far. Don't attempt this casually.
3. **AWS account has a low Lambda concurrency quota (raised from 10 to a requested 100 for `L-B99A9384` after the §12.8 incident) — outside Terraform's control.** Any future feature that fans out per-item Lambda invocations should batch its concurrency deliberately, not assume the AWS default of 1,000.
4. **Any new backend or Terraform change is not live until a real `terraform apply` runs in Terraform Cloud org `RSHL2136`, workspace `Y62DB`.** There is no Terraform Cloud connector available to the agent — applies must be triggered by the repo owner directly, and live behavior should always be re-verified with the Cognito `curl` pattern in §5 afterward, not assumed from a successful `terraform validate` alone.
5. **`edit`-tool and naive-regex hiccups** (agent-side, not project-side): malformed tool parameters have occasionally thrown a `JSONDecodeError` on file edits (immediately fixed by retrying with corrected parameters); a naive regex for stripping the `cloud{}` block breaks on its nested `workspaces{}` block (fixed by switching to brace-depth counting, per §6). Both are now known, resolved patterns — worth knowing about if either resurfaces.

---

## 9. How to Resume From Zero Context

1. Read this document top to bottom before touching anything.
2. `git log --oneline` in `/home/user/workspace/Y62DB` (or a fresh clone of `rtrivgreg/Y62DB`) — if `HEAD` is still `7e4c701`, nothing has changed since this snapshot. If it's moved on, read the newer commit messages and the corresponding new `§12.N` section(s) appended to `docs/BLUEPRINT.md` first.
3. Check the Terraform Cloud workspace's run history (`app.terraform.io`, org `RSHL2136`, workspace `Y62DB`) to see whether the most recent code changes have actually been applied — this document can only describe what was true at snapshot time, not what's true now.
4. Re-run the Cognito `curl` verification pattern (§5) against the live `api_base_url` to confirm current real-world behavior before assuming anything from written documentation, including this file.
5. `api/README.md` is the canonical API request/response contract; `schemas/access-patterns.md` is the canonical data-model doc. Read both before making changes outside what's already described here.
6. `docs/BLUEPRINT.md` is the full, unabridged project history (1,196+ lines) — read it for complete rationale on any decision this summary compresses. If anything in either document conflicts with what's actually in the repo or in AWS, trust the repo/AWS — these documents describe intent and history, not necessarily today's exact state.
7. `ui/TEST_PLAN.md` is the manual QA checklist — check which boxes are already ticked before re-running tests that have already passed.
8. Standing rule for any further work: validate every change (`pytest` / `terraform validate` / `npm run build` as applicable) before committing, document it as a new `§12.N` entry in `docs/BLUEPRINT.md`, and get explicit confirmation of the exact diff and commit message before pushing to `rtrivgreg/Y62DB` or applying in Terraform Cloud.
