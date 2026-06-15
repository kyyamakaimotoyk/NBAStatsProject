# versions.tf is the boostrap. Terraform needs to know which provider plugin to download and which version.
# Pins the Terraform CLI version and declares the AWS provider so 'terraform init' knows what to fetch.

# Copied from https://registry.terraform.io/providers/hashicorp/aws/latest
# Selecting provider here: AWS
terraform {
  required_version = ">= 1.6" #This is the terraform TOOL
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0" #This is the AWS provider plugin downloaded by init
    }
  }
}
