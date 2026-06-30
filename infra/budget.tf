# =============================================================================
# Cost guardrail: monthly AWS Budget with email alerts (Week 4.2)
# =============================================================================
# Catches a RUNAWAY bill (a mistake that doubles spend), not normal variation.
# Current baseline is ~$45-50/mo, so the limit has headroom above it. AWS Budgets
# emails the subscriber directly (no SNS confirmation dance needed).
# =============================================================================

variable "alert_email" {
  type        = string
  description = "Email for budget + CloudWatch alerts. Set in terraform.tfvars (gitignored) so it stays out of the repo."
}

variable "monthly_budget_usd" {
  type        = string
  default     = "75"
  description = "Monthly cost budget in USD. ~$50 baseline today; 75 leaves headroom to flag a real overrun without noise."
}

resource "aws_budgets_budget" "monthly" {
  name         = "${var.project}-monthly"
  budget_type  = "COST"
  limit_amount = var.monthly_budget_usd
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Early warning: spending has passed 80% of the budget this month.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  # You've gone over budget.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  # Forecast says you're TRENDING to exceed budget — catches a runaway early,
  # before the actual bill lands.
  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.alert_email]
  }
}
