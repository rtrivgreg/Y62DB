variable "aws_region" {
  type        = string
  description = "AWS region for DynamoDB tables."
  default     = "us-east-1"
}

variable "environment" {
  type        = string
  description = "Environment name."
  default     = "dev"
}

variable "config_rules_table_name" {
  type        = string
  default     = "config_rules"
}

variable "config_rule_parameters_table_name" {
  type        = string
  default     = "config_rule_parameters"
}
