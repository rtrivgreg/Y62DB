# Y62DB loader

Seeds `RULE_PROFILE` and `PARAMETER_DEF` items directly into the single
Y62DB DynamoDB table, by parsing AWS Config managed-rule metadata out of a
`config-rules-all`-style Terraform module.

This is the single-table successor to an earlier two-table version of this
script (see git history: `Update loader.py`, etc.) that wrote flat rows into
separate `config_rules` / `config_rule_parameters` tables. That schema
predates the single-table redesign in
[`schemas/access-patterns.md`](../schemas/access-patterns.md) and isn't
compatible with it — the CRUD API (`api/`) only ever reads/writes
`RULE_BINDING` items in the single table, and expects canonical rule and
parameter data to live there too, as `RULE_PROFILE`/`PARAMETER_DEF` items.
See [`docs/BLUEPRINT.md`](../docs/BLUEPRINT.md) for the fuller history.

The two legacy tables (`config_rules`, 801 items; `config_rule_parameters`,
669 items, confirmed live in `us-east-1` as of 2026-08-02) are not touched
by this script and are not read by anything else in this repo. **They are
not Y62DB's to manage** — they belong to a separate, unrelated Python
application and must be retained permanently regardless of anything this
repo does (confirmed by the repo owner 2026-08-02). This loader creates an
additional, independent copy of similar data in the single table for
Y62DB's own use — it is not a migration that supersedes or retires the
legacy tables. See `docs/BLUEPRINT.md` §11 for the full history.

## Setup

```bash
pip install -r requirements.txt
```

## Usage

Start with `--dry-run` and `--dump-json-dir` to inspect the normalized
output before writing anything:

```bash
python3 loader.py \
  --locals-file ~/repos/config-rules-all/vendor/niaid/managed_rules_locals.tf \
  --variables-file ~/repos/config-rules-all/vendor/niaid/managed_rules_variables.tf \
  --table y62db-config-rule-catalog \
  --region us-east-1 \
  --dry-run --dump-json-dir out
```

Then run for real:

```bash
python3 loader.py \
  --locals-file ~/repos/config-rules-all/vendor/niaid/managed_rules_locals.tf \
  --variables-file ~/repos/config-rules-all/vendor/niaid/managed_rules_variables.tf \
  --table y62db-config-rule-catalog \
  --region us-east-1
```

Use `--rule-limit N` to seed only the first `N` rules while testing against
the real source data.

## Item shapes written

```
RULE_PROFILE
  pk = RULE#<rule_id>
  sk = PROFILE#<rule_id>
  entity_type, rule_id, source_identifier, description, severity, scopes,
  managed_rule

PARAMETER_DEF
  pk = RULE#<rule_id>
  sk = PARAMDEF#<parameter_name>
  entity_type, rule_id, parameter_name, data_type, required, default_value,
  source_variable, placeholder_value
```

`rule_id` is always the plain rule slug (e.g. `access-keys-rotated`), never
prefixed with `RULE#` — the prefix is applied only when building `pk`/`sk`,
matching the convention already used by the CRUD API's
`_pk`/`_gsi1sk` helpers in `api/src/common/dynamodb.py`.

**Scope note:** parsed `resource_types_scope` values are kept as a `scopes`
attribute on the `RULE_PROFILE` item rather than emitted as separate
`SCOPE_DEF` items. `access-patterns.md` defines a `SCOPE_DEF` entity type
for "valid scope usage guidance" but doesn't specify how that maps from
this source data, and the parsed data here only carries one resource-type
list per rule with no additional guidance content. Populating `SCOPE_DEF`
is deliberately deferred rather than guessing at an unconfirmed shape — the
scope data itself isn't lost, it's just not yet split into its own entity
type.

## Testing

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
```

Tests run against a small synthetic HCL fixture in `tests/fixtures/` (two
rules, one with a parameter block) — they verify item shape and key
construction, not volume. Full-volume verification against the real
`config-rules-all` source (roughly 800 rules) can only be done by running
this script directly, since that repo isn't part of this workspace.
