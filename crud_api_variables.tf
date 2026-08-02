# ---------------------------------------------------------------------------
# Variables for the CRUD API layer (Lambda + API Gateway) that sits on top of
# the single-table y62db-config-rule-catalog design (see terraform/dynamodb.tf
# for the table definition; not currently applied through this TFC workspace).
# Kept in a separate file from the legacy config_rules/config_rule_parameters
# variables in variables.tf to avoid touching that resource set.
# ---------------------------------------------------------------------------

variable "crud_api_name" {
  description = "Name prefix for the CRUD API's Lambda, IAM role, and API Gateway resources."
  type        = string
  default     = "y62db-rule-catalog-api"
}

variable "dynamodb_table_name" {
  description = "Name of the existing y62db-config-rule-catalog DynamoDB table (not created by this workspace)."
  type        = string
  default     = "y62db-config-rule-catalog"
}

variable "dynamodb_gsi1_name" {
  description = "Name of the existing GSI used for group-based binding lookups (gsi1pk/gsi1sk)."
  type        = string
  default     = "gsi1-group-bindings"
}

variable "lambda_runtime" {
  description = "Python runtime for the CRUD API Lambda function."
  type        = string
  default     = "python3.12"
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 10
}

variable "lambda_memory_size" {
  description = "Lambda memory size in MB."
  type        = number
  default     = 256
}

variable "log_retention_days" {
  description = "CloudWatch Logs retention in days for the Lambda function."
  type        = number
  default     = 14
}

variable "tags" {
  description = "Extra tags applied to CRUD API resources, in addition to the provider's default_tags."
  type        = map(string)
  default     = {}
}
