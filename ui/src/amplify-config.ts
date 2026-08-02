/**
 * Amplify configuration for the Y62DB Bindings UI.
 *
 * This app does NOT provision its own Amplify Gen 2 backend (no `amplify/`
 * folder, no `npx ampx sandbox`). Both the Cognito User Pool and the REST
 * API are already created and managed by Terraform in the Y62DB repo root
 * (`crud_api_cognito.tf`, `crud_api_gateway.tf`) and applied to the
 * `RSHL2136`/`Y62DB` Terraform Cloud workspace. This file wires Amplify's
 * client libraries (`aws-amplify`, `@aws-amplify/ui-react`) to those
 * *existing* resources — Amplify's documented pattern for "bring your own
 * backend" rather than duplicating infrastructure that's already built.
 *
 * Values below come directly from the applied Terraform outputs
 * (`terraform output`), confirmed live 2026-08-02 — see docs/BLUEPRINT.md
 * §7 and §12.2 in the repo root for the verification record. If the stack
 * is ever re-applied and these identifiers change, update them here to
 * match `terraform output` again.
 */
import { Amplify } from "aws-amplify";

export const AWS_REGION = "us-east-1";

/** From `terraform output cognito_user_pool_id` */
export const USER_POOL_ID = "us-east-1_5OUP1L4hf";

/** From `terraform output cognito_user_pool_client_id` */
export const USER_POOL_CLIENT_ID = "2eruh11a9kc2lbdd286q282ofb";

/** From `terraform output api_base_url` */
export const API_BASE_URL =
  "https://3lkxt728eh.execute-api.us-east-1.amazonaws.com/dev";

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: USER_POOL_ID,
      userPoolClientId: USER_POOL_CLIENT_ID,
    },
  },
});
