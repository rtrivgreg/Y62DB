data "archive_file" "crud_api_lambda_package" {
  type        = "zip"
  source_dir  = "${path.module}/api/src"
  output_path = "${path.module}/build/crud_api_lambda_package.zip"
  excludes    = ["__pycache__"]
}

resource "aws_cloudwatch_log_group" "crud_api_lambda" {
  name              = "/aws/lambda/${var.crud_api_name}-${var.environment}"
  retention_in_days = var.log_retention_days
  tags              = var.tags
}

resource "aws_lambda_function" "crud_api" {
  function_name    = "${var.crud_api_name}-${var.environment}"
  role             = aws_iam_role.crud_api_lambda_exec.arn
  handler          = "handler.lambda_handler"
  runtime          = var.lambda_runtime
  timeout          = var.lambda_timeout
  memory_size      = var.lambda_memory_size
  filename         = data.archive_file.crud_api_lambda_package.output_path
  source_code_hash = data.archive_file.crud_api_lambda_package.output_base64sha256

  environment {
    variables = {
      CONFIG_RULE_CATALOG_TABLE = data.aws_dynamodb_table.rule_catalog.name
      CONFIG_RULE_CATALOG_GSI1  = var.dynamodb_gsi1_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.crud_api_lambda]

  tags = var.tags
}
