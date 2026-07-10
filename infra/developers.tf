# =============================================================================
# Developer access: IAM user (identity) + read-only role (permissions)
# =============================================================================
# The user itself can do almost nothing — sign in, change its own password,
# enroll its own MFA device, and assume the read-only role. All real
# permissions live on the role, and assuming it REQUIRES MFA. Same principle
# as github_oidc.tf: identities carry no standing permissions; roles do.
#
# What the role grants: the AWS-managed ReadOnlyAccess policy — CloudWatch
# logs, ECS task inspection, S3 reads (model bundles, ingest drops, CF logs),
# ECR, CloudFront. Notably it does NOT include secretsmanager:GetSecretValue,
# so the rotating RDS master password stays out of reach.
#
# What is deliberately NOT here (create by hand; see README of this walkthrough):
#   - the console password (aws iam create-login-profile) — a Terraform
#     login_profile would store the password in tfstate forever, same reason
#     the home-ingest access key is manual (see ingest.tf).
#   - access keys — console + MFA only until a CLI need actually appears.
# =============================================================================

variable "dev_email" {
  type        = string
  description = "New developer's email — used as their IAM username. Set in terraform.tfvars (gitignored), not here."
}

resource "aws_iam_user" "dev" {
  name = var.dev_email
  tags = {
    Name = "${var.project}-developer"
  }
}

# --- The user's own (tiny) permissions -------------------------------------

# Console self-service: view the password policy, change own password, enroll
# own virtual MFA device. Scoped to the user's own ARN via ${aws:username}.
# Deliberately excludes iam:DeactivateMFADevice / DeleteVirtualMFADevice —
# only the account admin can remove a lost MFA, so a hijacked session can't
# strip its own MFA.
data "aws_iam_policy_document" "dev_self_manage" {
  statement {
    sid = "ViewAccountBasics"
    actions = [
      "iam:GetAccountPasswordPolicy",
      "iam:ListVirtualMFADevices",
    ]
    resources = ["*"]
  }
  statement {
    sid = "ManageOwnPassword"
    actions = [
      "iam:ChangePassword",
      "iam:GetUser",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:user/$${aws:username}"]
  }
  statement {
    sid       = "CreateOwnMfa"
    actions   = ["iam:CreateVirtualMFADevice"]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:mfa/$${aws:username}"]
  }
  statement {
    sid = "EnrollOwnMfa"
    actions = [
      "iam:EnableMFADevice",
      "iam:ListMFADevices",
      "iam:ResyncMFADevice",
    ]
    resources = ["arn:aws:iam::${data.aws_caller_identity.current.account_id}:user/$${aws:username}"]
  }
}

resource "aws_iam_user_policy" "dev_self_manage" {
  name   = "${var.project}-dev-self-manage"
  user   = aws_iam_user.dev.name
  policy = data.aws_iam_policy_document.dev_self_manage.json
}

# The one capability the user carries: permission to assume the read-only role.
data "aws_iam_policy_document" "dev_assume_readonly" {
  statement {
    actions   = ["sts:AssumeRole"]
    resources = [aws_iam_role.dev_readonly.arn]
  }
}

resource "aws_iam_user_policy" "dev_assume_readonly" {
  name   = "${var.project}-dev-assume-readonly"
  user   = aws_iam_user.dev.name
  policy = data.aws_iam_policy_document.dev_assume_readonly.json
}

# --- The role that holds the actual permissions -----------------------------

# Trust policy: only this user may assume, and only with MFA in the session.
# (Console "Switch role" satisfies this automatically when the user signed in
# with MFA; CLI assume-role must pass --serial-number/--token-code.)
data "aws_iam_policy_document" "dev_readonly_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = [aws_iam_user.dev.arn]
    }
    condition {
      test     = "Bool"
      variable = "aws:MultiFactorAuthPresent"
      values   = ["true"]
    }
  }
}

resource "aws_iam_role" "dev_readonly" {
  name                 = "${var.project}-dev-readonly"
  assume_role_policy   = data.aws_iam_policy_document.dev_readonly_trust.json
  max_session_duration = 14400 # 4h console sessions instead of the 1h default
}

resource "aws_iam_role_policy_attachment" "dev_readonly" {
  role       = aws_iam_role.dev_readonly.name
  policy_arn = "arn:aws:iam::aws:policy/ReadOnlyAccess"
}

# --- Handy outputs for the invite email -------------------------------------

output "dev_console_signin_url" {
  value       = "https://${data.aws_caller_identity.current.account_id}.signin.aws.amazon.com/console"
  description = "Where the developer signs in with their IAM username (email) + password"
}

output "dev_switch_role_url" {
  value       = "https://signin.aws.amazon.com/switchrole?account=${data.aws_caller_identity.current.account_id}&roleName=${aws_iam_role.dev_readonly.name}&displayName=nba-readonly"
  description = "One-click console 'Switch role' link into the read-only role (after MFA sign-in)"
}
