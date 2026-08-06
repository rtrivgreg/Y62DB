"""
Live AWS identifiers for the Y62DB Bindings TUI.

Deliberately kept in lockstep with `ui/src/amplify-config.ts` — both the
Cognito User Pool and the REST API are already created and managed by
Terraform in the Y62DB repo root (`crud_api_cognito.tf`,
`crud_api_gateway.tf`). This TUI is a second, independent client against
that same existing backend — no new AWS resources of its own.

If the stack is ever re-applied and these identifiers change, update them
here AND in `ui/src/amplify-config.ts` to match `terraform output` again.
"""

AWS_REGION = "us-east-1"

# From `terraform output cognito_user_pool_client_id`
USER_POOL_CLIENT_ID = "2eruh11a9kc2lbdd286q282ofb"

# From `terraform output api_base_url`
API_BASE_URL = "https://3lkxt728eh.execute-api.us-east-1.amazonaws.com/dev"
