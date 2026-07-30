provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Y62DB"
      ManagedBy   = "terraform"
      Environment = var.environment
    }
  }
}
