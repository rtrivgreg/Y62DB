pip install python-hcl2

Run pattern
Run the Terraform Cloud remote apply first so the tables already exist.

Run the Python loader afterward from a trusted environment that has AWS credentials and network access to DynamoDB.

Start with --dry-run plus --dump-json-dir so you can inspect the normalized output before writing anything.

Example:

bash
python3 ~/repos/Y62DB/loader/loader.py --locals-file ~/repos/config-rules-all/vendor/niaid/managed_rules_locals.tf --variables-file ~/repos/config-rules-all/vendor/niaid/managed_rules_variables.tf --rules-table config_rules --parameters-table config_rule_parameters --region us-east-1 --dry-run --dump-json-dir out
Then live load:

bash
python3 ~/repos/Y62DB/loader/loader.py \
  --locals-file ~/repos/config-rules-all/vendor/niaid/managed_rules_locals.tf \
  --variables-file ~/repos/config-rules-all/vendor/niaid/managed_rules_variables.tf \
  --rules-table config_rules \
  --parameters-table config_rule_parameters \
  --region us-east-1


Important caveat
The script above intentionally keeps the parameter-variable parsing conservative. If managed_rules_variables.tf uses richer type expressions than python-hcl2 returns cleanly, the next refinement would be to parse that file with a text-based fallback so you can recover optional attribute metadata more completely.


This following command:
python3 ~/repos/Y62DB/loader/loader.py --locals-file ~/repos/config-rules-all/vendor/niaid/managed_rules_locals.tf --variables-file ~/repos/config-rules-all/vendor/niaid/managed_rules_variables.tf --rules-table config_rules --parameters-table config_rule_parameters --region us-east-1 --dry-run --dump-json-dir out


produces rules as expected:
{
    "rule_id": "RULE#workspaces-user-volume-encryption-enabled",
    "rule_name": "workspaces-user-volume-encryption-enabled",
    "source_identifier": "WORKSPACES_USER_VOLUME_ENCRYPTION_ENABLED",
    "description": "Checks if an Amazon WorkSpace volume has the user volume encryption settings set to enabled. This rule is NON_COMPLIANT if the encryption setting is not enabled for the user volume.",
    "severity": "Medium",
    "scopes": [
      "AWS::WorkSpaces::Workspace"
    ],
    "input_var": ""
  },
  {
    "rule_id": "RULE#workspaces-workspace-tagged",
    "rule_name": "workspaces-workspace-tagged",
    "source_identifier": "WORKSPACES_WORKSPACE_TAGGED",
    "description": "Checks if Amazon WorkSpaces workspaces have tags. Optionally, you can specify tag keys. The rule is NON_COMPLIANT if there are no tags or if the specified tag keys are not present. The rule does not check for tags starting with aws: .",
    "severity": "Medium",
    "scopes": [
      "AWS::WorkSpaces::Workspace"
    ],
    "input_var": "workspaces_workspace_tagged_parameters"
  }
  
parameters.json is an empty json array
[
]

