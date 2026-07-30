resource "aws_dynamodb_table_item" "rules" {
  for_each   = local.rules
  table_name = aws_dynamodb_table.config_rules.name
  hash_key   = aws_dynamodb_table.config_rules.hash_key

  item = jsonencode({
    rule_id           = { S = each.value.rule_id }
    rule_name         = { S = each.value.rule_name }
    source_identifier = { S = each.value.source_identifier }
    description       = { S = each.value.description }
    severity          = { S = each.value.severity }
    input_var         = { S = each.value.input_var }
    scopes            = { SS = each.value.scopes }
  })
}
