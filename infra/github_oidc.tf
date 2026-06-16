# =============================================================================
# GitHub Actions -> AWS via OIDC (Week 3.6)
# =============================================================================
# No long-lived AWS keys in GitHub. A workflow run presents a short-lived OIDC
# token asserting "I'm repo X, branch main"; AWS trusts GitHub's OIDC provider,
# verifies that claim, and issues temporary credentials for a role with exactly
# the deploy permissions. Nothing to store or rotate.
# =============================================================================

variable "github_repo" {
  type        = string
  default     = "kyyamakaimotoyk/NBAStatsProject"
  description = "owner/repo allowed to assume the deploy role"
}

# Register GitHub's OIDC identity provider in this account.
# Note: since 2023 AWS verifies the token against GitHub's published keys, so the
# thumbprint is no longer security-critical — but the argument is still required.
# Both long-standing GitHub thumbprints are listed for robustness.
resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  thumbprint_list = [
    "6938fd4d98bab03faadb97b34396831e3780aea1",
    "1c58a3a8518e8759bf075b76b750d4f2df264fcd",
  ]
}

# Who may assume the deploy role: only OIDC tokens from THIS repo, on main.
# (Scoping `sub` to refs/heads/main means a PR branch can't assume it — deploys
#  only happen from main.)
data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    effect  = "Allow"

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringLike"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_deploy" {
  name               = "${var.project}-github-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_assume.json
}

# Exactly the permissions the two workflows need — nothing more.
data "aws_iam_policy_document" "github_deploy" {
  # ECR login (token call must be unscoped).
  statement {
    sid       = "EcrAuth"
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  # Push/pull images to our two repos only.
  statement {
    sid = "EcrPush"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [
      aws_ecr_repository.api.arn,
      aws_ecr_repository.pipeline.arn,
    ]
  }

  # Trigger a rolling redeploy of the API service (re-pulls :latest).
  statement {
    sid       = "EcsDeploy"
    actions   = ["ecs:UpdateService", "ecs:DescribeServices"]
    resources = ["*"]
  }

  # Upload the built site (sync --delete needs list + put + delete).
  statement {
    sid       = "S3List"
    actions   = ["s3:ListBucket"]
    resources = [aws_s3_bucket.site.arn]
  }
  statement {
    sid       = "S3Objects"
    actions   = ["s3:PutObject", "s3:DeleteObject"]
    resources = ["${aws_s3_bucket.site.arn}/*"]
  }

  # Bust the CDN cache after a frontend deploy.
  statement {
    sid       = "CfInvalidate"
    actions   = ["cloudfront:CreateInvalidation"]
    resources = [aws_cloudfront_distribution.site.arn]
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name   = "${var.project}-github-deploy"
  role   = aws_iam_role.github_deploy.id
  policy = data.aws_iam_policy_document.github_deploy.json
}
