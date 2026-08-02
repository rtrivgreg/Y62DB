# REST API matching the API contract in README.md:
#   /rules/{ruleId}/bindings                    -> GET (list bindings for a rule), POST (create binding)
#   /rules/{ruleId}/bindings/{group}/{binding}  -> GET (read), PUT (replace payload), DELETE (remove)
#   /groups/{group}/bindings                    -> GET (list bindings for a group, via gsi1)
# Every method integrates with the same Lambda function (AWS_PROXY), which
# routes internally based on httpMethod + resource (see src/handler.py).

resource "aws_api_gateway_rest_api" "rule_catalog_api" {
  name        = "${var.crud_api_name}-${var.environment}"
  description = "CRUD REST API for AWS Config rule-to-group bindings, backed by y62db-config-rule-catalog."

  endpoint_configuration {
    types = ["REGIONAL"]
  }

  tags = var.tags
}

# ---- /rules/{ruleId}/bindings ------------------------------------------------

resource "aws_api_gateway_resource" "rules" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  parent_id   = aws_api_gateway_rest_api.rule_catalog_api.root_resource_id
  path_part   = "rules"
}

resource "aws_api_gateway_resource" "rule_id" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  parent_id   = aws_api_gateway_resource.rules.id
  path_part   = "{ruleId}"
}

# ---- /rules (no {ruleId}) -- list distinct rule IDs, powers UI fuzzy search --

resource "aws_api_gateway_method" "rules_get" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.rules.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "rules_get" {
  rest_api_id             = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id             = aws_api_gateway_resource.rules.id
  http_method             = aws_api_gateway_method.rules_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_api.invoke_arn
}

resource "aws_api_gateway_method" "rules_options" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.rules.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "rules_options" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.rules.id
  http_method = aws_api_gateway_method.rules_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "rules_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.rules.id
  http_method = aws_api_gateway_method.rules_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "rules_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.rules.id
  http_method = aws_api_gateway_method.rules_options.http_method
  status_code = aws_api_gateway_method_response.rules_options_200.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
  depends_on = [aws_api_gateway_integration.rules_options]
}

resource "aws_api_gateway_resource" "rule_bindings" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  parent_id   = aws_api_gateway_resource.rule_id.id
  path_part   = "bindings"
}

resource "aws_api_gateway_method" "rule_bindings_get" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.rule_bindings.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.path.ruleId" = true
  }
}

resource "aws_api_gateway_integration" "rule_bindings_get" {
  rest_api_id             = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id             = aws_api_gateway_resource.rule_bindings.id
  http_method             = aws_api_gateway_method.rule_bindings_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_api.invoke_arn
}

resource "aws_api_gateway_method" "rule_bindings_post" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.rule_bindings.id
  http_method   = "POST"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.path.ruleId" = true
  }
}

resource "aws_api_gateway_integration" "rule_bindings_post" {
  rest_api_id             = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id             = aws_api_gateway_resource.rule_bindings.id
  http_method             = aws_api_gateway_method.rule_bindings_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_api.invoke_arn
}

resource "aws_api_gateway_method" "rule_bindings_options" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.rule_bindings.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "rule_bindings_options" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.rule_bindings.id
  http_method = aws_api_gateway_method.rule_bindings_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "rule_bindings_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.rule_bindings.id
  http_method = aws_api_gateway_method.rule_bindings_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "rule_bindings_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.rule_bindings.id
  http_method = aws_api_gateway_method.rule_bindings_options.http_method
  status_code = aws_api_gateway_method_response.rule_bindings_options_200.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,POST,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
  depends_on = [aws_api_gateway_integration.rule_bindings_options]
}

# ---- /rules/{ruleId}/bindings/{group}/{binding} -------------------------------

resource "aws_api_gateway_resource" "rule_binding_group" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  parent_id   = aws_api_gateway_resource.rule_bindings.id
  path_part   = "{group}"
}

resource "aws_api_gateway_resource" "rule_binding_name" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  parent_id   = aws_api_gateway_resource.rule_binding_group.id
  path_part   = "{binding}"
}

resource "aws_api_gateway_method" "rule_binding_get" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.rule_binding_name.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.path.ruleId"  = true
    "method.request.path.group"   = true
    "method.request.path.binding" = true
  }
}

resource "aws_api_gateway_integration" "rule_binding_get" {
  rest_api_id             = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id             = aws_api_gateway_resource.rule_binding_name.id
  http_method             = aws_api_gateway_method.rule_binding_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_api.invoke_arn
}

resource "aws_api_gateway_method" "rule_binding_put" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.rule_binding_name.id
  http_method   = "PUT"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.path.ruleId"  = true
    "method.request.path.group"   = true
    "method.request.path.binding" = true
  }
}

resource "aws_api_gateway_integration" "rule_binding_put" {
  rest_api_id             = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id             = aws_api_gateway_resource.rule_binding_name.id
  http_method             = aws_api_gateway_method.rule_binding_put.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_api.invoke_arn
}

resource "aws_api_gateway_method" "rule_binding_delete" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.rule_binding_name.id
  http_method   = "DELETE"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.path.ruleId"  = true
    "method.request.path.group"   = true
    "method.request.path.binding" = true
  }
}

resource "aws_api_gateway_integration" "rule_binding_delete" {
  rest_api_id             = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id             = aws_api_gateway_resource.rule_binding_name.id
  http_method             = aws_api_gateway_method.rule_binding_delete.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_api.invoke_arn
}

resource "aws_api_gateway_method" "rule_binding_options" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.rule_binding_name.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "rule_binding_options" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.rule_binding_name.id
  http_method = aws_api_gateway_method.rule_binding_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "rule_binding_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.rule_binding_name.id
  http_method = aws_api_gateway_method.rule_binding_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "rule_binding_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.rule_binding_name.id
  http_method = aws_api_gateway_method.rule_binding_options.http_method
  status_code = aws_api_gateway_method_response.rule_binding_options_200.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,PUT,DELETE,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
  depends_on = [aws_api_gateway_integration.rule_binding_options]
}

# ---- /groups/{group}/bindings -------------------------------------------------

resource "aws_api_gateway_resource" "groups" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  parent_id   = aws_api_gateway_rest_api.rule_catalog_api.root_resource_id
  path_part   = "groups"
}

resource "aws_api_gateway_resource" "group_id" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  parent_id   = aws_api_gateway_resource.groups.id
  path_part   = "{group}"
}

# ---- /groups (no {group}) -- list distinct groups, powers UI fuzzy search --

resource "aws_api_gateway_method" "groups_get" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.groups.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
}

resource "aws_api_gateway_integration" "groups_get" {
  rest_api_id             = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id             = aws_api_gateway_resource.groups.id
  http_method             = aws_api_gateway_method.groups_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_api.invoke_arn
}

resource "aws_api_gateway_method" "groups_options" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.groups.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "groups_options" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.groups.id
  http_method = aws_api_gateway_method.groups_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "groups_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.groups.id
  http_method = aws_api_gateway_method.groups_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "groups_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.groups.id
  http_method = aws_api_gateway_method.groups_options.http_method
  status_code = aws_api_gateway_method_response.groups_options_200.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
  depends_on = [aws_api_gateway_integration.groups_options]
}

resource "aws_api_gateway_resource" "group_bindings" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  parent_id   = aws_api_gateway_resource.group_id.id
  path_part   = "bindings"
}

resource "aws_api_gateway_method" "group_bindings_get" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.group_bindings.id
  http_method   = "GET"
  authorization = "COGNITO_USER_POOLS"
  authorizer_id = aws_api_gateway_authorizer.cognito.id
  request_parameters = {
    "method.request.path.group" = true
  }
}

resource "aws_api_gateway_integration" "group_bindings_get" {
  rest_api_id             = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id             = aws_api_gateway_resource.group_bindings.id
  http_method             = aws_api_gateway_method.group_bindings_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.crud_api.invoke_arn
}

resource "aws_api_gateway_method" "group_bindings_options" {
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id   = aws_api_gateway_resource.group_bindings.id
  http_method   = "OPTIONS"
  authorization = "NONE"
}

resource "aws_api_gateway_integration" "group_bindings_options" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.group_bindings.id
  http_method = aws_api_gateway_method.group_bindings_options.http_method
  type        = "MOCK"
  request_templates = {
    "application/json" = "{\"statusCode\": 200}"
  }
}

resource "aws_api_gateway_method_response" "group_bindings_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.group_bindings.id
  http_method = aws_api_gateway_method.group_bindings_options.http_method
  status_code = "200"
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = true
    "method.response.header.Access-Control-Allow-Methods" = true
    "method.response.header.Access-Control-Allow-Origin"  = true
  }
}

resource "aws_api_gateway_integration_response" "group_bindings_options_200" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id
  resource_id = aws_api_gateway_resource.group_bindings.id
  http_method = aws_api_gateway_method.group_bindings_options.http_method
  status_code = aws_api_gateway_method_response.group_bindings_options_200.status_code
  response_parameters = {
    "method.response.header.Access-Control-Allow-Headers" = "'Content-Type,Authorization'"
    "method.response.header.Access-Control-Allow-Methods" = "'GET,OPTIONS'"
    "method.response.header.Access-Control-Allow-Origin"  = "'*'"
  }
  depends_on = [aws_api_gateway_integration.group_bindings_options]
}

# ---- Deployment & stage ------------------------------------------------------

resource "aws_api_gateway_deployment" "rule_catalog_api" {
  rest_api_id = aws_api_gateway_rest_api.rule_catalog_api.id

  # Force a new deployment whenever any route/integration changes.
  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.rule_bindings.id,
      aws_api_gateway_resource.rule_binding_group.id,
      aws_api_gateway_resource.rule_binding_name.id,
      aws_api_gateway_resource.group_bindings.id,
      aws_api_gateway_method.rule_bindings_get.id,
      aws_api_gateway_method.rule_bindings_post.id,
      aws_api_gateway_method.rule_binding_get.id,
      aws_api_gateway_method.rule_binding_put.id,
      aws_api_gateway_method.rule_binding_delete.id,
      aws_api_gateway_method.group_bindings_get.id,
      aws_api_gateway_method.rules_get.id,
      aws_api_gateway_method.groups_get.id,
      aws_api_gateway_integration.rule_bindings_get.id,
      aws_api_gateway_integration.rule_bindings_post.id,
      aws_api_gateway_integration.rule_binding_get.id,
      aws_api_gateway_integration.rule_binding_put.id,
      aws_api_gateway_integration.rule_binding_delete.id,
      aws_api_gateway_integration.group_bindings_get.id,
      aws_api_gateway_integration.rules_get.id,
      aws_api_gateway_integration.groups_get.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.rule_bindings_get,
    aws_api_gateway_integration.rule_bindings_post,
    aws_api_gateway_integration.rule_binding_get,
    aws_api_gateway_integration.rule_binding_put,
    aws_api_gateway_integration.rule_binding_delete,
    aws_api_gateway_integration.group_bindings_get,
    aws_api_gateway_integration.rules_get,
    aws_api_gateway_integration.groups_get,
  ]
}

resource "aws_api_gateway_stage" "rule_catalog_api" {
  deployment_id = aws_api_gateway_deployment.rule_catalog_api.id
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  stage_name    = var.environment
  tags          = var.tags
}

resource "aws_lambda_permission" "apigw_invoke" {
  statement_id  = "AllowAPIGatewayInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.crud_api.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.rule_catalog_api.execution_arn}/*/*"
}
