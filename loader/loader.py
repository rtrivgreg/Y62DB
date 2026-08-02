#!/usr/bin/env python3
"""
Loader for the Y62DB single-table config-rule catalog.

Parses AWS Config managed-rule metadata out of a config-rules-all-style
Terraform module (``managed_rules_locals.tf`` + ``managed_rules_variables.tf``)
and writes ``RULE_PROFILE`` and ``PARAMETER_DEF`` items directly into the
single DynamoDB table described in ``schemas/access-patterns.md``.

This supersedes the older two-table version of this script (see git
history), which wrote flat rows into separate ``config_rules`` /
``config_rule_parameters`` tables. That schema predates the single-table
redesign and is not compatible with it -- CRUD tooling (``api/``) only
ever reads/writes ``RULE_BINDING`` items in the single table, and expects
canonical rule/parameter data to live there too. See ``docs/BLUEPRINT.md``
for the full history and rationale behind this rewrite.

Item shapes written (see schemas/access-patterns.md for the source of truth):

    RULE_PROFILE
        pk = RULE#<rule_id>
        sk = PROFILE#<rule_id>

    PARAMETER_DEF
        pk = RULE#<rule_id>
        sk = PARAMDEF#<parameter_name>

Note on scope: parsed ``resource_types_scope`` values are currently kept as
a plain ``scopes`` attribute on the RULE_PROFILE item rather than emitted as
separate SCOPE_DEF items. The access-patterns doc defines a SCOPE_DEF entity
type for "valid scope usage guidance," but doesn't specify how that maps
from this source data (e.g. one SCOPE_DEF per resource type vs. one per
rule), and the current parsed data only carries a single list of resource
types per rule with no additional guidance/notes content. Rather than
invent a shape, SCOPE_DEF population is deliberately deferred -- the scope
data is not lost (it's still on RULE_PROFILE), but nothing here writes
SCOPE_DEF items yet. Revisit this once there's a concrete access pattern
that needs SCOPE_DEF specifically.
"""
import argparse
import json
import re
import time
from pathlib import Path

import boto3
import hcl2

DEFAULT_LOCALS = "managed_rules_locals.tf"
DEFAULT_VARIABLES = "managed_rules_variables.tf"


def load_hcl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return hcl2.load(f)


def load_variables_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def clean_string(value):
    if not isinstance(value, str):
        return value
    value = value.strip()
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    if len(value) >= 2 and value[0] == "'" and value[-1] == "'":
        return value[1:-1]
    return value


def extract_input_var(value):
    if not isinstance(value, str):
        return None
    value = clean_string(value)
    if value.startswith("${var.") and value.endswith("}"):
        return value[6:-1]
    if value.startswith("var."):
        return value[4:]
    return None


def load_managed_rules(locals_path: Path):
    data = load_hcl(locals_path)
    return data["locals"][0]["managed_rules"]


def normalize_parameter_variables_from_text(params_text: str) -> dict:
    """Recover optional-attribute metadata from raw HCL text.

    Kept text-based (rather than relying solely on python-hcl2's parse of
    ``variables.tf``) because ``managed_rules_variables.tf`` uses
    ``optional(type, default)`` expressions inside ``object({...})`` type
    blocks that python-hcl2 does not resolve cleanly on its own.
    """
    var_pattern = re.compile(
        r'variable\s+"([A-Za-z0-9_]+)"\s*{(.*?)(?=^variable\s+"|\Z)',
        re.S | re.M,
    )

    optional_attr_pattern = re.compile(
        r'([A-Za-z0-9_]+)\s*=\s*optional\((string|number|bool|boolean)(?:,\s*([^)]+))?\)'
    )

    default_block_pattern = re.compile(
        r'default\s*=\s*{(.*?)}',
        re.S,
    )

    normalized = {}

    for var_name, body in var_pattern.findall(params_text):
        if not var_name.endswith("_parameters"):
            continue

        attrs = []
        type_block = re.search(r'type\s*=\s*object\(\s*{(.*?)}\s*\)', body, re.S)
        if type_block:
            for key, typ, default in optional_attr_pattern.findall(type_block.group(1)):
                attrs.append(
                    {
                        "name": key,
                        "type": typ,
                        "default": default.strip() if default else None,
                    }
                )

        defaults = {}
        default_block = default_block_pattern.search(body)
        if default_block:
            for line in default_block.group(1).splitlines():
                line = line.strip().rstrip(",")
                if not line or "=" not in line:
                    continue
                key, value = [x.strip() for x in line.split("=", 1)]
                defaults[key] = clean_string(value)

        normalized[var_name] = {
            "attrs": attrs,
            "default": defaults,
        }

    return normalized


def normalize_rules(managed_rules: dict) -> list[dict]:
    """Normalize parsed locals into logical rule records.

    ``rule_id`` here is the plain slug (e.g. ``access-keys-rotated``), with
    no ``RULE#`` prefix -- the prefix is applied only when building the
    actual DynamoDB pk/sk, matching the convention already used by the
    CRUD API (see ``api/src/common/dynamodb.py``'s ``_pk``/``_gsi1sk``
    helpers). The legacy version of this script baked the prefix directly
    into the ``rule_id`` field, which does not match that convention.
    """
    rules = []
    for rule_name, rule_def in managed_rules.items():
        rule_id = clean_string(rule_name)
        input_var = extract_input_var(rule_def.get("input_parameters"))

        rules.append(
            {
                "rule_id": rule_id,
                "source_identifier": clean_string(rule_def.get("identifier")),
                "description": clean_string(rule_def.get("description", "")),
                "severity": clean_string(rule_def.get("severity", "")),
                "scopes": [clean_string(x) for x in rule_def.get("resource_types_scope", [])],
                "input_var": input_var or "",
            }
        )
    return rules


def build_parameter_records(rules: list[dict], variable_defs: dict) -> list[dict]:
    """Build logical (pre-DynamoDB-shape) parameter records for each rule."""
    records = []

    for rule in rules:
        input_var = rule.get("input_var")
        if not input_var:
            continue

        var_def = variable_defs.get(input_var, {})
        defaults = var_def.get("default", {})
        attrs = var_def.get("attrs", [])

        seen = set()

        for key, value in defaults.items():
            records.append(
                {
                    "rule_id": rule["rule_id"],
                    "parameter_name": key,
                    "data_type": "string",
                    "required": True,
                    "default_value": "" if value is None else str(value),
                    "source_variable": input_var,
                    "placeholder_value": "" if value is None else str(value),
                }
            )
            seen.add(key)

        for attr in attrs:
            name = attr["name"]
            if name in seen:
                continue
            default_value = attr.get("default")
            records.append(
                {
                    "rule_id": rule["rule_id"],
                    "parameter_name": name,
                    "data_type": attr.get("type", "string"),
                    "required": False,
                    "default_value": "" if default_value is None else str(default_value),
                    "source_variable": input_var,
                    "placeholder_value": "" if default_value is None else "optional_string",
                }
            )

    return records


def build_rule_profile_items(rules: list[dict]) -> list[dict]:
    """Map logical rule records to RULE_PROFILE DynamoDB items."""
    items = []
    for rule in rules:
        rule_id = rule["rule_id"]
        items.append(
            {
                "pk": f"RULE#{rule_id}",
                "sk": f"PROFILE#{rule_id}",
                "entity_type": "RULE_PROFILE",
                "rule_id": rule_id,
                "source_identifier": rule.get("source_identifier", ""),
                "description": rule.get("description", ""),
                "severity": rule.get("severity", ""),
                "scopes": rule.get("scopes", []),
                "managed_rule": True,
            }
        )
    return items


def build_parameter_def_items(parameter_records: list[dict]) -> list[dict]:
    """Map logical parameter records to PARAMETER_DEF DynamoDB items."""
    items = []
    for record in parameter_records:
        rule_id = record["rule_id"]
        parameter_name = record["parameter_name"]
        items.append(
            {
                "pk": f"RULE#{rule_id}",
                "sk": f"PARAMDEF#{parameter_name}",
                "entity_type": "PARAMETER_DEF",
                "rule_id": rule_id,
                "parameter_name": parameter_name,
                "data_type": record.get("data_type", "string"),
                "required": record.get("required", False),
                "default_value": record.get("default_value", ""),
                "source_variable": record.get("source_variable", ""),
                "placeholder_value": record.get("placeholder_value", ""),
            }
        )
    return items


SET_FIELDS = {"scopes"}


def to_ddb_item(item: dict) -> dict:
    ddb = {}

    for k, v in item.items():
        if v is None:
            continue

        if isinstance(v, bool):
            ddb[k] = {"BOOL": v}

        elif isinstance(v, (int, float)):
            ddb[k] = {"N": str(v)}

        elif isinstance(v, list):
            values = [str(x) for x in v if x is not None and str(x) != ""]
            if not values:
                continue

            if k in SET_FIELDS:
                ddb[k] = {"SS": sorted(set(values))}
            else:
                ddb[k] = {"L": [{"S": x} for x in values]}

        else:
            s = str(v)
            if s != "":
                ddb[k] = {"S": s}

    return ddb


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def batch_write(client, table_name: str, items: list[dict], max_attempts: int = 10):
    for batch_num, batch in enumerate(chunked(items, 25), start=1):
        request_items = {
            table_name: [{"PutRequest": {"Item": to_ddb_item(item)}} for item in batch]
        }

        attempt = 0
        delay = 1.0

        while request_items.get(table_name):
            resp = client.batch_write_item(RequestItems=request_items)
            request_items = resp.get("UnprocessedItems", {})
            unprocessed = len(request_items.get(table_name, []))

            if not unprocessed:
                break

            attempt += 1
            if attempt >= max_attempts:
                raise RuntimeError(
                    f"batch_write failed for table={table_name} batch={batch_num} "
                    f"after {attempt} retries; unprocessed={unprocessed}"
                )

            print(
                f"Retrying table={table_name} batch={batch_num} "
                f"attempt={attempt} unprocessed={unprocessed} sleep={delay:.1f}s"
            )
            time.sleep(delay)
            delay = min(delay * 2, 16)


def main():
    parser = argparse.ArgumentParser(
        description="Seed RULE_PROFILE and PARAMETER_DEF items into the Y62DB single table."
    )
    parser.add_argument("--locals-file", default=DEFAULT_LOCALS)
    parser.add_argument("--variables-file", default=DEFAULT_VARIABLES)
    parser.add_argument(
        "--table",
        required=True,
        help="Single DynamoDB table name, e.g. y62db-config-rule-catalog",
    )
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dump-json-dir")
    parser.add_argument("--rule-limit", type=int, default=0)
    args = parser.parse_args()

    managed_rules = load_managed_rules(Path(args.locals_file))
    variables_text = load_variables_text(Path(args.variables_file))
    variable_defs = normalize_parameter_variables_from_text(variables_text)

    rules = normalize_rules(managed_rules)
    if args.rule_limit > 0:
        rules = rules[:args.rule_limit]

    parameter_records = build_parameter_records(rules, variable_defs)

    rule_profile_items = build_rule_profile_items(rules)
    parameter_def_items = build_parameter_def_items(parameter_records)

    print(f"rule_profile_items={len(rule_profile_items)} parameter_def_items={len(parameter_def_items)}")

    if args.dump_json_dir:
        outdir = Path(args.dump_json_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "rule_profile_items.json").write_text(
            json.dumps(rule_profile_items, indent=2), encoding="utf-8"
        )
        (outdir / "parameter_def_items.json").write_text(
            json.dumps(parameter_def_items, indent=2), encoding="utf-8"
        )

    if args.dry_run:
        return

    ddb = boto3.client("dynamodb", region_name=args.region)
    batch_write(ddb, args.table, rule_profile_items)
    batch_write(ddb, args.table, parameter_def_items)
    print("load complete")


if __name__ == "__main__":
    main()
