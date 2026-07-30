output "config_rules_table_name" {
  value = aws_dynamodb_table.config_rules.name
}

output "config_rules_table_arn" {
  value = aws_dynamodb_table.config_rules.arn
}

output "config_rule_parameters_table_name" {
  value = aws_dynamodb_table.config_rule_parameters.name
}

output "config_rule_parameters_table_arn" {
  value = aws_dynamodb_table.config_rule_parameters.arn
}
