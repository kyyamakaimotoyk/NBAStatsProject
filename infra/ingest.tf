# =============================================================================
# Residential-ingest handoff: home PC -> S3 -> nightly pipeline -> RDS
# =============================================================================
# stats.nba.com hard-blocks AWS IPs (proven 2026-06-17; cdn.nba.com followed),
# so raw NBA data is fetched at home — the one place with a residential IP that
# works — and handed to the cloud through S3:
#
#   home PC (Task Scheduler, ~7am ET)
#     nba_api ingest -> local MySQL -> export new rows -> parquet
#     -> s3://<this bucket>/pending/<date>/<table>.parquet
#   nightly pipeline task (11am ET)
#     load stage: read pending/ -> upsert RDS -> move drop to processed/
#
# Why S3 and not opening RDS to the home IP: flipping publicly_accessible
# would force the DB into public subnets (instance REPLACEMENT), pin a security
# group to a changing home IP, and add a third victim to the weekly password
# rotation. The S3 drop needs none of that — the home box holds one
# narrowly-scoped IAM key that can only put files here.
# =============================================================================

resource "aws_s3_bucket" "ingest" {
  bucket = "${var.project}-ingest-${data.aws_caller_identity.current.account_id}"
  tags = {
    Name = "${var.project}-ingest"
  }
}

resource "aws_s3_bucket_public_access_block" "ingest" {
  bucket                  = aws_s3_bucket.ingest.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ingest" {
  bucket = aws_s3_bucket.ingest.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Drops are transient: once loaded into RDS they're just clutter. processed/
# copies are kept ~30 days for debugging ("what exactly did we load Tuesday?"),
# then expire. If a drop sits in pending/ that long, something is wrong and the
# freshness alarm will have said so long before.
resource "aws_s3_bucket_lifecycle_configuration" "ingest" {
  bucket = aws_s3_bucket.ingest.id
  rule {
    id     = "expire-ingest-drops"
    status = "Enabled"
    filter {}
    expiration {
      days = 30
    }
  }
}


# -----------------------------------------------------------------------------
# The home PC's identity: an IAM *user* (machines outside AWS can't assume
# roles without something to authenticate with — a long-lived access key is
# the standard pattern for a single trusted box). Scope is deliberately tiny:
# it can put files into this one bucket and list it. It cannot read models,
# touch the DB, or see anything else in the account.
# -----------------------------------------------------------------------------
resource "aws_iam_user" "home_ingest" {
  name = "${var.project}-home-ingest"
}

data "aws_iam_policy_document" "home_ingest" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.ingest.arn}/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.ingest.arn]
  }
}

resource "aws_iam_user_policy" "home_ingest" {
  name   = "${var.project}-home-ingest-s3"
  user   = aws_iam_user.home_ingest.name
  policy = data.aws_iam_policy_document.home_ingest.json
}

# NOTE: the access key is created by hand (`aws iam create-access-key`), NOT in
# Terraform — an aws_iam_access_key resource would store the secret in the
# tfstate file forever.


# -----------------------------------------------------------------------------
# The pipeline task's side of the handoff: read drops, and move them to
# processed/ after a successful load (a move is copy + delete in S3 terms).
# Kept as a separate policy so the existing read-models grant stays untouched.
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "ecs_task_ingest" {
  statement {
    actions   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.ingest.arn}/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.ingest.arn]
  }
}

resource "aws_iam_role_policy" "ecs_task_ingest" {
  name   = "${var.project}-ecs-task-ingest"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_ingest.json
}
