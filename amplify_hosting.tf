# ---------------------------------------------------------------------------
# AWS Amplify Hosting (CI/CD) for ui/, the bindings CRUD frontend built on
# top of the Lambda + API Gateway CRUD API (crud_api_*.tf) and Cognito
# (crud_api_cognito.tf).
#
# Decision record (docs/BLUEPRINT.md §12.12):
#   - Terraform-managed (this file), not console-managed, for consistency
#     with the rest of the stack.
#   - Default *.amplifyapp.com domain -- no custom domain.
#   - main branch only -- no PR preview branches, no branch auto-creation.
#
# Monorepo build settings live in the checked-in amplify.yml at the repo
# root (uses Amplify's "applications" monorepo format with appRoot: ui), so
# build_spec is intentionally left unset here -- Amplify auto-detects it.
#
# NOTE: this requires the IAM role/policy that Terraform Cloud's AWS OIDC
# integration assumes to include amplify:* permissions (CreateApp,
# CreateBranch, UpdateApp, GetApp, GetBranch, TagResource, at minimum). That
# role is not defined in this repo -- if `terraform apply` fails with an
# AccessDenied error on any amplify:* action, the role's policy needs to be
# widened out-of-band (e.g. in whatever repo/console manages the OIDC role).
# ---------------------------------------------------------------------------

resource "aws_amplify_app" "bindings_ui" {
  name       = var.amplify_app_name
  repository = var.github_repository_url

  access_token = var.github_access_token

  platform = "WEB"

  # SPA fallback: any path not matching a real static asset serves
  # index.html with a 200 (not a real 404). Harmless today since ui/ has no
  # client-side router yet, but avoids a broken-deep-link surprise the
  # moment one is added.
  custom_rule {
    source = "/<*>"
    status = "404-200"
    target = "/index.html"
  }

  tags = {
    Project   = "Y62DB"
    Component = "bindings-ui"
  }
}

resource "aws_amplify_branch" "main" {
  app_id      = aws_amplify_app.bindings_ui.id
  branch_name = "main"
  stage       = "PRODUCTION"
  framework   = "React"

  enable_auto_build = true

  tags = {
    Project   = "Y62DB"
    Component = "bindings-ui"
  }
}
