# Y62DB

Y62DB is the catalog and control-plane data layer for curated AWS Config managed rule metadata, parameter values, scope values, and internal compliance flavors.[cite:129][cite:9][web:206] It exists to separate baseline AWS-managed rule inventory from organization-specific configuration choices so future tooling can generate consistent conformance packs, rule bundles, and policy outputs from a durable source of truth.[cite:129][web:79][web:503]

## Why this project exists

Y62DB was created after the limits of file-only and template-only rule management became clear in the broader `config-rules-all` workflow.[cite:129] AWS Config rules evaluate resource configuration settings, but the service does not provide a runtime schema-discovery model that is convenient for managing internal parameter and scope variants as reusable products, which makes a dedicated metadata layer valuable.[web:206][web:503]

The project’s genesis is practical rather than theoretical: baseline managed-rule definitions were already available from Terraform source and conformance-pack generation scripts, but internal users needed a way to curate parameter values, preserve explicit empty `InputParameters: {}` semantics, and support different internal security expectations without forking the entire source corpus.[cite:129][cite:9][cite:482] That combination drove the move toward a DynamoDB-backed catalog that can preserve baseline inventory while allowing controlled CRUD on curated overlays.[cite:129][web:496]

## Core purpose

The core purpose of Y62DB is to provide a stable catalog for three different layers of rule data:[cite:129][web:79]

- **Baseline inventory**: imported facts about AWS managed rules and parameter definitions from Terraform source and related generation inputs.[cite:129]
- **Curated configuration**: approved internal parameter values and scope selections used to express organizational policy intent.[cite:129][cite:482]
- **Group-specific flavors**: alternate bindings of the same logical managed rule for different internal organizational groups or compliance baselines.[cite:129]

This design follows DynamoDB guidance to model around access patterns, minimize unnecessary table sprawl, and document key structures explicitly for future maintainers.[web:496][web:459]

## Design principles

Y62DB is built around a few durable principles that should remain true even if the implementation evolves:[cite:129][web:497]

- Preserve the baseline source separately from curated edits so vendor inventory and internal policy decisions do not become conflated.[cite:129]
- Treat parameters and scope as first-class metadata, because those are the levers that turn a generic AWS managed rule into a deployable internal control.[cite:482][web:206]
- Favor explicitness over inference; for example, an empty parameter map can still be meaningful and should be represented intentionally.[cite:9]
- Model reads first, because DynamoDB works best when the table shape follows access patterns and item-collection design rather than relational decomposition.[web:470][web:459][web:30]
- Future-proof the repository with descriptive documentation, stable naming conventions, and item schemas that can tolerate additional internal group flavors over time.[web:497][web:499]

## Repository intent

This repository is intended to become the long-lived home for the DynamoDB-backed rule catalog and its surrounding tooling, not merely a one-time loader script collection.[cite:129] The working expectation is that Terraform manages the infrastructure, GitHub remains the source-control system for definitions and code, and downstream generators consume curated data from Y62DB to emit conformance-pack artifacts or other compliance outputs.[cite:129][cite:6]

At a minimum, the repository should continue to answer four future-maintainer questions clearly:[web:497][web:501]

1. What data is stored here?
2. Where did that data originate?
3. Which data is baseline versus curated?
4. How do internal group-specific flavors differ from one another?

## Expected contents

The project is expected to contain the following categories of content over time:[cite:129]

| Area | Purpose |
|---|---|
| Terraform infrastructure | Provision DynamoDB tables, indexes, IAM, and related AWS resources for the catalog.[cite:129][cite:6] |
| Loader utilities | Ingest baseline managed-rule definitions and parameter metadata from Terraform source files into DynamoDB.[cite:129] |
| Catalog schemas | Define item shapes for rule profiles, parameter definitions, scope definitions, bindings, and audit events.[cite:129] |
| CRUD services | Support controlled create, read, update, and delete operations for curated parameter and scope values.[cite:129] |
| Export/generator tools | Produce conformance-pack YAML or related outputs from curated catalog records.[cite:483][cite:482] |
| Documentation | Explain provenance, schema rules, access patterns, and operational expectations for future maintainers.[web:497][web:499] |

## Data domains

Y62DB should be understood as a catalog of related but distinct data domains rather than as a single flat rule list.[cite:129] The most important domains are the rule profile, parameter definition, scope definition, group binding, and audit trail, which map naturally to a single-table or limited-table DynamoDB model when keyed around access patterns.[web:470][web:473][web:30]

Recommended domain breakdown:

- **Rule profile**: one logical definition for a managed rule family, including identifier, description, and baseline metadata.[cite:129][web:79]
- **Parameter definition**: allowed parameter names, types, defaults, ranges, and validation hints for the rule.[cite:129]
- **Scope definition**: allowed scope selectors or resource-type constraints relevant to the rule.[cite:482][web:206]
- **Binding**: a deployable, curated combination of parameter values and scope values for a specific internal use case or organizational group.[cite:129]
- **Audit event**: an immutable history record of CRUD changes to curated items.[cite:129]

## Organizational flavors

A central reason Y62DB exists is to support multiple internal “flavors” of the same AWS Config managed rule without duplicating the baseline rule definition unnecessarily.[cite:129] For example, one organizational group may require a stricter `maxAccessKeyAge` value for `ACCESS_KEYS_ROTATED`, while another group may allow the AWS default or apply a different scope selection.[web:408][cite:482]

The long-term model therefore assumes that the baseline rule is global, while group-specific bindings carry the mutable values for parameters, scope, lifecycle state, and approval context.[cite:129] This aligns with DynamoDB item-collection patterns and with multi-tenant or grouped modeling strategies that rely on deliberate partition and sort key design for each access pattern.[web:485][web:486][web:30]

## Baseline and curated split

One of the most important future-proofing rules in this project is to keep imported baseline inventory separate from curated, organization-owned decisions.[cite:129] Baseline data answers “what AWS or the source corpus says exists,” while curated data answers “what this organization has decided to deploy or enforce.”[cite:129][web:79]

That split reduces accidental mutation of source-derived records, preserves provenance, and makes regeneration safer when upstream rule metadata changes.[cite:129][web:459] It also makes it easier to explain why the same managed rule may appear with multiple internal bindings across different organizational groups.[cite:129]

## Source of truth philosophy

Y62DB should be treated as the operational source of truth for curated parameter and scope values once data is promoted into the catalog, while imported Terraform and YAML sources remain the provenance source for baseline definitions.[cite:129][cite:482] This distinction matters because the project has already emphasized that both `InputParameters` and `Scope` need a trustworthy source-of-truth model rather than ad hoc reconstruction from generated outputs.[cite:482][cite:483]

Where no active parameters exist, explicit representation still matters; the prior workflow already established that `InputParameters: {}` is semantically meaningful and should not be treated as equivalent to field omission.[cite:9] Future code should preserve that explicitness when reading from or writing to the catalog.[cite:9]

## Suggested access patterns

The repository should continue documenting access patterns before schema changes are made, because DynamoDB design depends on them.[web:459][web:496] The core access patterns likely include:

- Get a rule profile and all its definitions and bindings.[cite:129][web:30]
- List all bindings for one organizational group.[cite:129][web:28]
- Read one exact group-specific flavor of one rule.[cite:129]
- Update a binding with optimistic locking using a version field.[web:458][web:462]
- Export all active bindings for a given internal program into a generated conformance-pack artifact.[cite:129][cite:483]

## Operational expectations

The infrastructure direction for this project is Terraform Cloud-centric with OIDC-oriented AWS authentication and GitHub-based source control, reflecting the broader operating model already used around related repositories.[cite:6][cite:129] That means future maintainers should expect infrastructure changes to be codified, reviewed, and applied through Terraform workflows rather than through console-only mutations.[cite:6]

For data operations, the repository should prefer idempotent loaders, conditional writes for mutable records, and explicit version attributes for concurrent CRUD safety, because optimistic locking is a common DynamoDB pattern for preventing lost updates.[web:458][web:462]

## Naming and stability

Long-term maintainability depends on stable naming conventions for keys, entity types, rule identifiers, and organizational-group identifiers.[web:497][web:499] Consistent prefixes such as `RULE#`, `PARAMDEF#`, `SCOPEDEF#`, `GROUP#`, and `AUDIT#` make the item model readable to humans and predictable for tooling, which is especially important in single-table DynamoDB designs.[web:459][web:470]

Future schema changes should prefer additive evolution over destructive rewrites whenever possible.[web:496] New item types, new group dimensions, and new export formats should be layered onto the model in a way that preserves existing consumers and historical records.[cite:129]

## Recommended repository structure

A future-proof repository structure could look like this:[web:499][cite:129]

```text
Y62DB/
├── README.md
├── terraform/
│   ├── tables.tf
│   ├── iam.tf
│   ├── outputs.tf
│   └── variables.tf
├── loader/
│   ├── loader.py
│   └── fixtures/
├── schemas/
│   ├── item-types.md
│   ├── access-patterns.md
│   └── examples/
├── generators/
│   ├── conformance-pack/
│   └── exports/
├── docs/
│   ├── provenance.md
│   ├── operations.md
│   └── decisions/
└── tests/
```

## Non-goals

To keep the project coherent, Y62DB should avoid becoming an unbounded dumping ground for every compliance artifact or every AWS Config experiment.[cite:129] It is not meant to replace AWS Config itself, nor to duplicate all upstream rule documentation, nor to store generated artifacts as the primary system of record.[web:206][web:79]

Its purpose is narrower and more durable: maintain curated, queryable control metadata that can be trusted by generators, admin tooling, and future automation.[cite:129]

## Maintenance guidance

Future maintainers should update this README whenever any of the following changes materially shift:[web:497][web:499]

- The project’s primary source inputs.
- The DynamoDB table layout or key design.
- The distinction between baseline and curated records.
- The list of supported organizational-group flavors.
- The authoritative generation path for conformance-pack outputs.

Schema decisions should also be recorded in lightweight architecture decision records under `docs/decisions/` so design intent is not lost in code alone.[web:499][web:501]

## Working summary

Y62DB is the durable catalog layer behind curated AWS Config managed-rule governance.[cite:129][web:503] Its job is to preserve baseline rule provenance, store explicit parameter and scope metadata, and support multiple internal organizational flavors without forcing duplication of the underlying managed-rule definition.[cite:129][cite:482]
