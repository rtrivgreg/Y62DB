variable "aws_region" {
  description = "AWS region for Y62DB"
  type        = string
}

variable "project_name" {
  description = "Project identifier"
  type        = string
  default     = "Y62DB"
}

variable "environment" {
  description = "Environment name"
  type        = string
  default     = "prod"
}

variable "repository_name" {
  description = "Source repository name"
  type        = string
  default     = "Y62DB"
}

variable "table_name" {
  description = "DynamoDB table name"
  type        = string
  default     = "y62db-config-rule-catalog"
}

variable "pitr_enabled" {
  description = "Enable point-in-time recovery"
  type        = bool
  default     = true
}

variable "kms_key_arn" {
  description = "Optional customer-managed KMS key ARN for DynamoDB SSE"
  type        = string
  default     = null
}
