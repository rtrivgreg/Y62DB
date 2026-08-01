# Y62DB access patterns

## Purpose

Y62DB stores AWS Config managed rule metadata and organizational-group-specific bindings.

The design keeps one canonical rule profile while allowing multiple internal "flavors" of the same rule through separate binding records.

`ACCESS_KEYS_ROTATED` may appear in examples because it is easy to explain, but it is only illustrative and does not limit the architecture.

## Design principles

- Use a single DynamoDB table with multiple entity types.
- Design keys from access patterns first.
- Keep canonical rule metadata separate from deployable group-specific bindings.
- Treat `organizational_group` as a first-class binding dimension, not as a casual attribute.
- Keep Terraform responsible for infrastructure underlayment, not mutable catalog rows.

## Base table keys

- `pk`
- `sk`

## Global secondary index keys

- `gsi1pk`
- `gsi1sk`

## Core entity types

### RULE_PROFILE

Canonical record for a managed rule.

- `pk = RULE#<rule_id>`
- `sk = PROFILE#<rule_id>`

Typical fields:

- `entity_type = RULE_PROFILE`
- `rule_id`
- `source_owner`
- `source_identifier`
- `trigger_type`
- `managed_rule = true`

### PARAMETER_DEF

Metadata about allowed or known rule parameters.

- `pk = RULE#<rule_id>`
- `sk = PARAMDEF#<parameter_name>`

Typical fields:

- `entity_type = PARAMETER_DEF`
- `rule_id`
- `parameter_name`
- `data_type`
- `required`
- `default_value`
- `description`

### SCOPE_DEF

Metadata or guidance about valid scope usage for a rule.

- `pk = RULE#<rule_id>`
- `sk = SCOPEDEF#<scope_name>`

Typical fields:

- `entity_type = SCOPE_DEF`
- `rule_id`
- `scope_name`
- `allowed_resource_types`
- `notes`

### RULE_BINDING

Deployable organizational flavor of a canonical rule.

- `pk = RULE#<rule_id>`
- `sk = GROUP#<group_id>#BINDING#<binding_id>`
- `gsi1pk = GROUP#<group_id>`
- `gsi1sk = RULE#<rule_id>#BINDING#<binding_id>`

Typical fields:

- `entity_type = RULE_BINDING`
- `rule_id`
- `organizational_group`
- `binding_id`
- `status`
- `parameter_values`
- `scope_values`
- `version`
- `created_by`
- `updated_at`

### ORG_GROUP

Metadata record for an internal group.

- `pk = GROUP#<group_id>`
- `sk = PROFILE#<group_id>`

Typical fields:

- `entity_type = ORG_GROUP`
- `group_id`
- `display_name`
- `owner`
- `description`

### AUDIT_EVENT

Immutable history item for rule or binding changes.

- `pk = RULE#<rule_id>`
- `sk = AUDIT#<timestamp>#<event_id>`

Typical fields:

- `entity_type = AUDIT_EVENT`
- `rule_id`
- `event_id`
- `event_type`
- `actor`
- `change_summary`

## Main access patterns

### 1. Get one rule and all related metadata

Purpose:
Retrieve the canonical rule profile, parameter definitions, scope definitions, bindings, and audit items for one rule.

Query:
- `pk = RULE#<rule_id>`

### 2. Get one exact flavor of one rule

Purpose:
Retrieve the binding for one specific organizational group and binding identifier.

Query:
- `pk = RULE#<rule_id>`
- `sk = GROUP#<group_id>#BINDING#<binding_id>`

### 3. List all bindings for one organizational group

Purpose:
Find every rule flavor assigned to a given internal group.

Query via GSI1:
- `gsi1pk = GROUP#<group_id>`

### 4. Export all active bindings for one group

Purpose:
Generate downstream artifacts such as conformance-pack-like outputs or internal policy bundles for one group.

Query via GSI1:
- `gsi1pk = GROUP#<group_id>`

Then filter or model for:
- `status = ACTIVE`

### 5. Review rule change history

Purpose:
Retrieve audit history for a rule.

Query:
- `pk = RULE#<rule_id>`
- `sk begins_with AUDIT#`

## Flavor model

A "flavor" is not a second copy of the rule.

A flavor is a `RULE_BINDING` record that points to the canonical rule and stores the organizational-group-specific choices for:

- parameters
- scope
- activation state
- version
- governance metadata

This allows one managed rule to support multiple internal compliance interpretations without duplicating the shared rule definition.

## Scope and parameter notes

AWS Config managed rules can be customized through scope and input parameters.

Because of that, Y62DB stores shared rule facts in canonical records and stores organizational differences in `RULE_BINDING`.

Some rules may allow empty scope or no active parameters, so downstream generation should preserve explicit empty structures when needed.

## Terraform boundary

Terraform creates and manages:

- the DynamoDB table
- keys and indexes
- encryption
- recovery settings
- outputs

Terraform does not manage every future row in the catalog.

Mutable records such as `RULE_PROFILE`, `PARAMETER_DEF`, `RULE_BINDING`, and `AUDIT_EVENT` should be created by loaders, CRUD tools, or application logic outside normal Terraform state management.
