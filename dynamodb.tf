resource "aws_dynamodb_table" "config_rules" {
  name         = var.config_rules_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "rule_id"

  attribute {
    name = "rule_id"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}

resource "aws_dynamodb_table" "config_rule_parameters" {
  name         = var.config_rule_parameters_table_name
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "rule_id"
  range_key    = "parameter_name"

  attribute {
    name = "rule_id"
    type = "S"
  }

  attribute {
    name = "parameter_name"
    type = "S"
  }

  point_in_time_recovery {
    enabled = true
  }

  server_side_encryption {
    enabled = true
  }
}
