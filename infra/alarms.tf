# =============================================================================
# CloudWatch alarms for the public API (Week 4.3)
# =============================================================================
# Two alarms that page you if the public API is unhealthy, delivered by email via
# an SNS topic. (The nightly-task-failure alarm is DEFERRED to pre-season: today
# the scheduled task legitimately finds "no games" and can't reach NBA data from
# AWS, so alarming on it would be constant false positives. Add it with the
# pre-season egress fix, when the task is actually expected to succeed.)
# =============================================================================


# -----------------------------------------------------------------------------
# SNS topic + email subscription (reuses var.alert_email from budget.tf)
# -----------------------------------------------------------------------------
# NOTE: an email SNS subscription must be CONFIRMED — AWS sends a "Confirm
# subscription" email after apply; click it or no alarm emails arrive.
resource "aws_sns_topic" "alerts" {
  name = "${var.project}-alerts"
}

resource "aws_sns_topic_subscription" "alerts_email" {
  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email
}


# -----------------------------------------------------------------------------
# Alarm 1: the API has no healthy task (service effectively down)
# -----------------------------------------------------------------------------
# HealthyHostCount is how many targets pass the ALB health check (/api/health).
# With desired_count = 1, this is normally 1; < 1 for 3 minutes = the API is down.
resource "aws_cloudwatch_metric_alarm" "api_unhealthy" {
  alarm_name          = "${var.project}-api-no-healthy-hosts"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HealthyHostCount"
  statistic           = "Minimum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching" # no data = assume bad (we want to know)

  dimensions = {
    TargetGroup  = aws_lb_target_group.api.arn_suffix
    LoadBalancer = aws_lb.main.arn_suffix
  }

  alarm_description = "API target group has no healthy task for 3 minutes."
  alarm_actions     = [aws_sns_topic.alerts.arn]
  ok_actions        = [aws_sns_topic.alerts.arn] # also notify on recovery
}


# -----------------------------------------------------------------------------
# Alarm 2: the API is throwing 5xx errors
# -----------------------------------------------------------------------------
# Target 5xx = the FastAPI app itself errored (DB down, unhandled exception, ...).
# > 5 in a 5-minute window trips it. Missing data = no errors = fine.
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.project}-api-5xx"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  dimensions = {
    TargetGroup  = aws_lb_target_group.api.arn_suffix
    LoadBalancer = aws_lb.main.arn_suffix
  }

  alarm_description = "API returned more than 5 HTTP 5xx responses in 5 minutes."
  alarm_actions     = [aws_sns_topic.alerts.arn]
}


# -----------------------------------------------------------------------------
# Alarm 3: the API can't talk to the database (added 2026-06-29 post-incident)
# -----------------------------------------------------------------------------
# WHY: the 2026-06-29 outage was invisible to the alarms above — /api/health
# returns 200 even when the DB is down (liveness, not readiness), so the ALB
# health check passed and the 5xx alarm needs sustained request volume to trip.
# This watches the API's OWN LOGS for the DB-connection exception, so the symptom
# itself pages us. A "metric filter" turns matching log lines into a CloudWatch
# metric we can alarm on. See docs/troubleshooting_lab.md.
resource "aws_cloudwatch_log_metric_filter" "api_db_errors" {
  name           = "${var.project}-api-db-errors"
  log_group_name = aws_cloudwatch_log_group.api.name

  # Matches both auth failures ("Access denied" after a secret rotation) and
  # connectivity failures — pymysql/SQLAlchemy raise OperationalError for both.
  pattern = "OperationalError"

  metric_transformation {
    name          = "ApiDbErrors"
    namespace     = "${var.project}/api"
    value         = "1"
    default_value = "0" # emit 0 when no match, so the metric always has data
  }
}

resource "aws_cloudwatch_metric_alarm" "api_db_errors" {
  alarm_name          = "${var.project}-api-db-errors"
  namespace           = "${var.project}/api"
  metric_name         = "ApiDbErrors"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold" # any DB error in 5 min = alarm
  treat_missing_data  = "notBreaching"

  alarm_description = "API logged a database OperationalError (stale password after rotation, or DB unreachable)."
  alarm_actions     = [aws_sns_topic.alerts.arn]
  ok_actions        = [aws_sns_topic.alerts.arn]
}
