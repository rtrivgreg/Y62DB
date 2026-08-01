output "y62db_table_name" {
  description = "Y62DB DynamoDB table name"
  value       = aws_dynamodb_table.y62db.name
}

output "y62db_table_arn" {
  description = "Y62DB DynamoDB table ARN"
  value       = aws_dynamodb_table.y62db.arn
}

output "y62db_gsi1_name" {
  description = "Group binding lookup index"
  value       = "gsi1-group-bindings"
}
