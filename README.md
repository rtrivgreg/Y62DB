Run pattern
Run the Terraform Cloud remote apply first so the tables already exist.

Run the Python loader afterward from a trusted environment that has AWS credentials and network access to DynamoDB.

Start with --dry-run plus --dump-json-dir so you can inspect the normalized output before writing anything.

Example:

bash
python3 load_config_rules.py \
  --locals-file managed_rules_locals.tf \
  --variables-file managed_rules_variables.tf \
  --rules-table config_rules \
  --parameters-table config_rule_parameters \
  --region us-east-1 \
  --dry-run \
  --dump-json-dir out
Then live load:

bash
python3 load_config_rules.py \
  --locals-file managed_rules_locals.tf \
  --variables-file managed_rules_variables.tf \
  --rules-table config_rules \
  --parameters-table config_rule_parameters \
  --region us-east-1
Important caveat
The script above intentionally keeps the parameter-variable parsing conservative. If managed_rules_variables.tf uses richer type expressions than python-hcl2 returns cleanly, the next refinement would be to parse that file with a text-based fallback so you can recover optional attribute metadata more completely.

