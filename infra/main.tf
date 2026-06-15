# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/caller_identity
#Use this data source to get the access to the effective Account ID, User ID, and ARN in which Terraform is authorized.
data "aws_caller_identity" "current" {}

# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/data-sources/availability_zones
# The Availability Zones data source allows access to the list of AWS Availability Zones which can be accessed by an AWS account within the region configured in the provider.
#
#This is different from the aws_availability_zone (singular) data source, which provides some details about a specific availability zone.
# Declaring the data source here
data "aws_availability_zones" "available" {
  state = "available"
}

