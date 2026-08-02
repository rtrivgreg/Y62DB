output "api_base_url" {
  description = "Base invoke URL for the deployed API."
  value       = aws_api_gateway_stage.rule_catalog_api.invoke_url
}

output "lambda_function_name" {
  value = aws_lambda_function.crud_api.function_name
}

output "dynamodb_table_name" {
  value = data.aws_dynamodb_table.rule_catalog.name
}

output "dynamodb_table_arn" {
  value = local.dynamodb_table_arn
}
