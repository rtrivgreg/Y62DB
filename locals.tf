locals {
  rules = {
    "RULE#access-keys-rotated" = {
      rule_id           = "RULE#access-keys-rotated"
      rule_name         = "access-keys-rotated"
      source_identifier = "ACCESS_KEYS_ROTATED"
      description       = "Checks whether access keys are rotated."
      severity          = "HIGH"
      scopes            = ["AWS::IAM::User"]
      input_var         = "access_keys_rotated_parameters"
    }
  }

  parameters = {
    "RULE#access-keys-rotated#maxAccessKeyAge" = {
      rule_id           = "RULE#access-keys-rotated"
      parameter_name    = "maxAccessKeyAge"
      parameter_type    = "number"
      is_required       = true
      default_value     = "90"
      placeholder_value = "90"
      source_variable   = "access_keys_rotated_parameters"
    }
  }
}
