#!/usr/bin/env python3
import argparse
import json
import time
from pathlib import Path

import boto3
import hcl2


DEFAULT_LOCALS = "managed_rules_locals.tf"
DEFAULT_VARIABLES = "managed_rules_variables.tf"


def load_hcl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return hcl2.load(f)


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


def load_variables_text(variables_path: Path):
    return variables_path.read_text(encoding="utf-8")


def normalize_rules(managed_rules: dict):
    rules = []
    for rule_name, rule_def in managed_rules.items():
        rule_name_clean = clean_string(rule_name)
        input_var = extract_input_var(rule_def.get("input_parameters"))

        rules.append(
            {
                "rule_id": f"RULE#{rule_name_clean}",
                "rule_name": rule_name_clean,
                "source_identifier": clean_string(rule_def.get("identifier")),
                "description": clean_string(rule_def.get("description", "")),
                "severity": clean_string(rule_def.get("severity", "")),
                "scopes": [clean_string(x) for x in rule_def.get("resource_types_scope", [])],
                "input_var": input_var or "",
            }
        )
    return rules


def parse_variables_with_hcl(variables_path: Path):
    data = load_hcl(variables_path)
    out = {}

    for var_block in data.get("variable", []):
        for var_name, body in var_block.items():
            if not var_name.endswith("_parameters"):
                continue

            attrs = []
            type_obj = body.get("type")
            defaults = body.get("default", {})

            if isinstance(defaults, list) and defaults:
                defaults = defaults[0]
            if defaults is None:
                defaults = {}
            if not isinstance(defaults, dict):
                defaults = {}

            if isinstance(type_obj, str):
                pass

            out[var_name] = {
                "attrs": attrs,
                "default": {k: clean_string(v) for k, v in defaults.items()},
            }

    return out


def build_parameter_items(rules, variable_defs):
    items = []

    for rule in rules:
        input_var = rule.get("input_var")
        if not input_var:
            continue

        var_def = variable_defs.get(input_var, {})
        defaults = var_def.get("default", {})
        attrs = var_def.get("attrs", [])

        seen = set()

        for key, value in defaults.items():
            items.append(
                {
                    "rule_id": rule["rule_id"],
                    "parameter_name": key,
                    "parameter_type": "string",
                    "is_required": True,
                    "default_value": "" if value is None else str(value),
                    "placeholder_value": "" if value is None else str(value),
                    "source_variable": input_var,
                }
            )
            seen.add(key)

        for attr in attrs:
            name = attr["name"]
            if name in seen:
                continue
            default_value = attr.get("default")
            items.append(
                {
                    "rule_id": rule["rule_id"],
                    "parameter_name": name,
                    "parameter_type": attr.get("type", "string"),
                    "is_required": False,
                    "default_value": "" if default_value is None else str(default_value),
                    "placeholder_value": "" if default_value is None else "optional_string",
                    "source_variable": input_var,
                }
            )

    return items


def to_ddb_item(item: dict):
    ddb = {}
    for k, v in item.items():
        if isinstance(v, bool):
            ddb[k] = {"BOOL": v}
        elif isinstance(v, list):
            if v:
                ddb[k] = {"SS": [str(x) for x in v]}
        else:
            s = "" if v is None else str(v)
            ddb[k] = {"S": s}
    return ddb


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def batch_write(client, table_name: str, items: list[dict]):
    for batch in chunked(items, 25):
        request_items = {
            table_name: [{"PutRequest": {"Item": to_ddb_item(item)}} for item in batch]
        }

        while request_items.get(table_name):
            resp = client.batch_write_item(RequestItems=request_items)
            unprocessed = resp.get("UnprocessedItems", {})
            request_items = unprocessed
            if request_items:
                time.sleep(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--locals-file", default=DEFAULT_LOCALS)
    parser.add_argument("--variables-file", default=DEFAULT_VARIABLES)
    parser.add_argument("--rules-table", required=True)
    parser.add_argument("--parameters-table", required=True)
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dump-json-dir")
    args = parser.parse_args()

    managed_rules = load_managed_rules(Path(args.locals_file))
    variable_defs = parse_variables_with_hcl(Path(args.variables_file))

    rules = normalize_rules(managed_rules)
    parameters = build_parameter_items(rules, variable_defs)

    if args.dump_json_dir:
        outdir = Path(args.dump_json_dir)
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "rules.json").write_text(json.dumps(rules, indent=2), encoding="utf-8")
        (outdir / "parameters.json").write_text(json.dumps(parameters, indent=2), encoding="utf-8")

    print(f"rules={len(rules)} parameters={len(parameters)}")

    if args.dry_run:
        return

    ddb = boto3.client("dynamodb", region_name=args.region)
    batch_write(ddb, args.rules_table, rules)
    batch_write(ddb, args.parameters_table, parameters)
    print("load complete")


if __name__ == "__main__":
    main()
