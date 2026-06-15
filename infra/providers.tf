# Using https://developer.hashicorp.com/terraform/language/block/provider as a reference

# Credentials are stored separately with aws CLI command "aws configure"
# I performed a read-only identity check "aws sts get-caller-identity"
provider "aws" {
  region = var.aws_region #defined in variables.tf
  default_tags {
    tags = {
      Project   = var.project #defined in variables.tf
      ManagedBy = "terraform"
    }
  }

}