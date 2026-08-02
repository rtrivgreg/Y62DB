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

output "cognito_user_pool_id" {
  description = "Cognito User Pool ID. Needed by the future Amplify frontend's Amplify.configure() Auth block."
  value       = aws_cognito_user_pool.rule_catalog_users.id
}

output "cognito_user_pool_client_id" {
  description = "Cognito User Pool Client ID (public, no secret). Needed by the future Amplify frontend's Amplify.configure() Auth block."
  value       = aws_cognito_user_pool_client.rule_catalog_ui.id
}
