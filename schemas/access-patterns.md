# Y62DB access patterns

## Purpose

Y62DB stores AWS Config managed rule metadata and group-specific bindings.

## Base table keys

- pk
- sk

## GSI keys

- gsi1pk
- gsi1sk

## Entity patterns

- RULE_PROFILE
  - pk = RULE#<rule_id>
  - sk = PROFILE#<rule_id>

- PARAMETER_DEF
  - pk = RULE#<rule_id>
  - sk = PARAMDEF#<parameter_name>

- SCOPE_DEF
  - pk = RULE#<rule_id>
  - sk = SCOPEDEF#<name>

- RULE_BINDING
  - pk = RULE#<rule_id>
  - sk = GROUP#<group_id>#BINDING#<binding_id>
  - gsi1pk = GROUP#<group_id>
  - gsi1sk = RULE#<rule_id>#BINDING#<binding_id>

- ORG_GROUP
  - pk = GROUP#<group_id>
  - sk = PROFILE#<group_id>

## Main access patterns

- Get one rule and all related records
- Get one exact group binding for a rule
- List all bindings for one organizational group
- Export bindings for one group into generated artifacts
