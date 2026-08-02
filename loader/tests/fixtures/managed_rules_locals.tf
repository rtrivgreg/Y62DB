locals {
  managed_rules = {
    "access-keys-rotated" = {
      identifier            = "ACCESS_KEYS_ROTATED"
      description           = "Checks whether access keys are rotated within the specified number of days."
      severity              = "Medium"
      resource_types_scope  = ["AWS::IAM::User"]
      input_parameters      = "${var.access_keys_rotated_parameters}"
    }
    "s3-bucket-versioning-enabled" = {
      identifier            = "S3_BUCKET_VERSIONING_ENABLED"
      description           = "Checks whether versioning is enabled for S3 buckets."
      severity              = "Low"
      resource_types_scope  = ["AWS::S3::Bucket"]
    }
  }
}
