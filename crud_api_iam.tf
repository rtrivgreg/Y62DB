data "aws_caller_identity" "current" {}

resource "aws_iam_role" "crud_api_lambda_exec" {
  name = "${var.crud_api_name}-lambda-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })

  tags = var.tags
}

resource "aws_iam_role_policy" "crud_api_lambda_dynamodb" {
  name = "${var.crud_api_name}-dynamodb-access-${var.environment}"
  role = aws_iam_role.crud_api_lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem",
        "dynamodb:Query",
        "dynamodb:Scan",
      ]
      # Scoped to the existing y62db-config-rule-catalog table + its
      # gsi1-group-bindings index only — least-privilege, no wildcard ARNs,
      # no table-creation permissions (this stack never manages the table).
      # Scan added for GET /rules and GET /groups
      # (list_all_rules_with_binding_status / list_distinct_groups) —
      # there's no GSI that enumerates distinct rule IDs or groups
      # directly, so those two read-only endpoints scan the base table and
      # dedupe/merge in the Lambda. GetItem + Query above also cover
      # GET /rules/{ruleId}/catalog (single PROFILE# item + PARAMDEF#
      # query, see docs/BLUEPRINT.md §12.11) — no new IAM grant needed.
      Resource = [
        local.dynamodb_table_arn,
        local.dynamodb_gsi1_arn,
      ]
    }]
  })
}

resource "aws_iam_role_policy_attachment" "crud_api_lambda_basic_execution" {
  role       = aws_iam_role.crud_api_lambda_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}
