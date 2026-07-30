resource "aws_dynamodb_table_item" "parameters" {
  for_each   = local.parameters
  table_name = aws_dynamodb_table.config_rule_parameters.name
  hash_key   = aws_dynamodb_table.config_rule_parameters.hash_key
  range_key  = aws_dynamodb_table.config_rule_parameters.range_key

  item = jsonencode({
    rule_id           = { S = each.value.rule_id }
    parameter_name    = { S = each.value.parameter_name }
    parameter_type    = { S = each.value.parameter_type }
    is_required       = { BOOL = each.value.is_required }
    default_value     = { S = each.value.default_value }
    placeholder_value = { S = each.value.placeholder_value }
    source_variable   = { S = each.value.source_variable }
  })
}
