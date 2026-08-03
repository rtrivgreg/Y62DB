# ---------------------------------------------------------------------------
# Variables for AWS Amplify Hosting (CI/CD for ui/, the bindings CRUD
# frontend). See amplify_hosting.tf for the resources and docs/BLUEPRINT.md
# §12.12 for the decision record (Terraform-managed, default amplifyapp.com
# domain, main branch only -- no PR previews).
# ---------------------------------------------------------------------------

variable "github_repository_url" {
  description = "HTTPS URL of the GitHub repository Amplify Hosting builds from."
  type        = string
  default     = "https://github.com/rtrivgreg/Y62DB"
}

variable "github_access_token" {
  description = <<-EOT
    GitHub personal access token (classic, 'repo' scope, or a fine-grained
    token with Contents: Read-only + Webhooks: Read & write on this repo)
    used once by Amplify to install a deploy key and a push webhook on the
    repository. AWS does not persist this token after app creation, but it
    is NOT marked as write-only by the Terraform AWS provider, so it will be
    written into Terraform state. Set this as a *sensitive* variable
    directly in the Terraform Cloud workspace UI -- never commit a real
    value, and never pass it to this variable via terraform.tfvars.
  EOT
  type        = string
  sensitive   = true
}

variable "amplify_app_name" {
  description = "Name of the Amplify Hosting app."
  type        = string
  default     = "y62db-bindings-ui"
}
