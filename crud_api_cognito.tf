# ---------------------------------------------------------------------------
# Cognito User Pool backing authentication for the CRUD API and, later, the
# Amplify-hosted form UI. Both API Gateway (via the COGNITO_USER_POOLS
# authorizer below) and the future Amplify frontend's Auth category point at
# this same pool, so there is exactly one identity source for this
# initiative — resolves the open decision in docs/BLUEPRINT.md §8.2.
# ---------------------------------------------------------------------------

resource "aws_cognito_user_pool" "rule_catalog_users" {
  name = "${var.crud_api_name}-users-${var.environment}"

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = false
  }

  auto_verified_attributes = ["email"]

  tags = var.tags
}

resource "aws_cognito_user_pool_client" "rule_catalog_ui" {
  name         = "${var.crud_api_name}-ui-client-${var.environment}"
  user_pool_id = aws_cognito_user_pool.rule_catalog_users.id

  # Public client (no secret) — matches how a browser-based Amplify/React app
  # authenticates: SRP username/password via Amplify's Auth category
  # (e.g. the <Authenticator> component), not OAuth Hosted UI, so no
  # callback/logout URLs are configured here.
  generate_secret = false

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
    # ALLOW_USER_PASSWORD_AUTH is added purely so a bearer token can be
    # obtained with a plain `aws cognito-idp initiate-auth` CLI call for
    # smoke-testing, without needing an SRP-capable client library. The
    # real Amplify frontend will still use SRP via <Authenticator> —
    # this doesn't replace that, it just adds a second supported flow on
    # the same client.
    "ALLOW_USER_PASSWORD_AUTH",
  ]

  access_token_validity  = 1
  id_token_validity      = 1
  refresh_token_validity = 30

  token_validity_units {
    access_token  = "hours"
    id_token      = "hours"
    refresh_token = "days"
  }
}

resource "aws_api_gateway_authorizer" "cognito" {
  name          = "${var.crud_api_name}-cognito-authorizer-${var.environment}"
  rest_api_id   = aws_api_gateway_rest_api.rule_catalog_api.id
  type          = "COGNITO_USER_POOLS"
  provider_arns = [aws_cognito_user_pool.rule_catalog_users.arn]
}
