# Read-only lookup of the existing table. Intentionally a data source, not a
# resource: this workspace's dynamodb.tf/locals.tf/outputs.tf manage the
# separate legacy config_rules/config_rule_parameters tables, and this CRUD
# API must never compete with whatever actually created
# y62db-config-rule-catalog for ownership of that resource.
data "aws_dynamodb_table" "rule_catalog" {
  name = var.dynamodb_table_name
}

locals {
  dynamodb_table_arn = data.aws_dynamodb_table.rule_catalog.arn
  dynamodb_gsi1_arn  = "${data.aws_dynamodb_table.rule_catalog.arn}/index/${var.dynamodb_gsi1_name}"
}
