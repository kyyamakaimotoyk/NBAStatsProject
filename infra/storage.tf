
# Creating a s3 object store for the ML models
resource "aws_s3_bucket" "models" {
  bucket = "${var.project}-models-${data.aws_caller_identity.current.account_id}" # suffixing the s3 bucket with my unique account_id because it has to be globally unique
  tags = {
    Name = "${var.project}-models"
  }
}

# https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/s3_bucket_public_access_block
# Manages S3 bucket-level Public Access Block configuration.
# help you manage public access to Amazon S3 resources. By default, new buckets, access points, and objects don't allow
# public access. However, users can modify bucket policies, access point policies, or object permissions to allow public access.
# S3 Block Public Access settings override these policies and permissions so that you can limit public access to these resources.

#The split-resource pattern: versioning/encryption/public-access are not arguments on aws_s3_bucket — they're separate resources that each reference
#  aws_s3_bucket.models.id. The AWS API models them as independent settings, and the provider mirrors that.
resource "aws_s3_bucket_public_access_block" "models" {
  bucket                  = aws_s3_bucket.models.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "models" {
  bucket = aws_s3_bucket.models.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "models" {
  bucket = aws_s3_bucket.models.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}