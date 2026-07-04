# =============================================================================
# CloudWatch alarms: public API (Week 4.3) + nightly pipeline (2026-07-02)
# =============================================================================
# Alarms 1-3 page you if the public API is unhealthy. Alarms 4-6 watch the
# nightly pipeline — added with the residential-ingest handoff (ingest.tf),
# which made the nightly task's success actually expected, closing the
# long-deferred "nightly task failure alarm" item. All email via one SNS topic.
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


# -----------------------------------------------------------------------------
# Alarm 4: the nightly job says its data is STALE (home ingest broke)
# -----------------------------------------------------------------------------
# batch_predict_today runs freshness checks after loading S3 drops and prints
# "DATA_FRESHNESS_ALERT: <reason>" when the newest drop is >26h old or when
# yesterday's scheduled games have no final boxscores. The job itself still
# exits 0 (predicting with slightly stale form beats not predicting) — this
# alarm is how you HEAR about it.
resource "aws_cloudwatch_log_metric_filter" "pipeline_freshness" {
  name           = "${var.project}-pipeline-freshness"
  log_group_name = aws_cloudwatch_log_group.pipeline.name
  pattern        = "DATA_FRESHNESS_ALERT"

  metric_transformation {
    name          = "PipelineFreshnessAlerts"
    namespace     = "${var.project}/pipeline"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "pipeline_freshness" {
  alarm_name          = "${var.project}-pipeline-data-stale"
  namespace           = "${var.project}/pipeline"
  metric_name         = "PipelineFreshnessAlerts"
  statistic           = "Sum"
  period              = 86400 # daily job -> daily window
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_description = "Nightly pipeline reported stale data (home ingest missed a day, or yesterday's boxscores never arrived)."
  alarm_actions     = [aws_sns_topic.alerts.arn]
  ok_actions        = [aws_sns_topic.alerts.arn]
}


# -----------------------------------------------------------------------------
# Alarm 5: the pipeline logged an ERROR (S3 load failed, prediction crashed, ...)
# -----------------------------------------------------------------------------
# Case-sensitive on purpose: our own failure paths print the token "ERROR"
# (s3_ingest_loader, batch_predict_today), while benign fallback chatter like
# "Error fetching league schedule" (title case) does not match.
resource "aws_cloudwatch_log_metric_filter" "pipeline_errors" {
  name           = "${var.project}-pipeline-errors"
  log_group_name = aws_cloudwatch_log_group.pipeline.name
  pattern        = "ERROR"

  metric_transformation {
    name          = "PipelineErrors"
    namespace     = "${var.project}/pipeline"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "pipeline_errors" {
  alarm_name          = "${var.project}-pipeline-errors"
  namespace           = "${var.project}/pipeline"
  metric_name         = "PipelineErrors"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_description = "Nightly pipeline logged an ERROR line (S3 drop failed to load, prediction error, ...)."
  alarm_actions     = [aws_sns_topic.alerts.arn]
  ok_actions        = [aws_sns_topic.alerts.arn]
}


# -----------------------------------------------------------------------------
# Alarm 6: dead-man switch — the nightly job DIDN'T RUN (or died mid-run)
# -----------------------------------------------------------------------------
# The inverse of the others: batch_predict_today prints "NIGHTLY_RUN_OK" only on
# a clean finish, and this alarm fires when that heartbeat goes MISSING. Catches
# what no error-based alarm can: the schedule not firing, the image failing to
# pull, the task dying before it logs anything.
#
# Shape: two 12-hour buckets, alarm when BOTH contain no heartbeat. One 24h
# bucket would flap on scheduler jitter (a run at 11:00 and the next at 11:04
# leaves a moment where the trailing day has zero heartbeats); with 2x12h, a
# single daily heartbeat always lands in one of the two buckets.
resource "aws_cloudwatch_log_metric_filter" "pipeline_heartbeat" {
  name           = "${var.project}-pipeline-heartbeat"
  log_group_name = aws_cloudwatch_log_group.pipeline.name
  pattern        = "NIGHTLY_RUN_OK"

  metric_transformation {
    name          = "PipelineHeartbeat"
    namespace     = "${var.project}/pipeline"
    value         = "1"
    default_value = "0"
  }
}

# -----------------------------------------------------------------------------
# Alarm 7: model drift — displayed probabilities went dishonest on live games
# -----------------------------------------------------------------------------
# The E19/E21 lesson: the 2025-26 calibrator incident was visible in live data
# for weeks (+0.28 gap between mean displayed home-prob and the actual home-win
# rate) but nothing was watching. The nightly job now prints MODEL_DRIFT_ALERT
# when a model's trailing-21-day gap exceeds 0.12 (>=60 graded games, so this
# is naturally silent in the offseason).
resource "aws_cloudwatch_log_metric_filter" "pipeline_drift" {
  name           = "${var.project}-pipeline-drift"
  log_group_name = aws_cloudwatch_log_group.pipeline.name
  pattern        = "MODEL_DRIFT_ALERT"

  metric_transformation {
    name          = "PipelineModelDrift"
    namespace     = "${var.project}/pipeline"
    value         = "1"
    default_value = "0"
  }
}

resource "aws_cloudwatch_metric_alarm" "pipeline_drift" {
  alarm_name          = "${var.project}-pipeline-model-drift"
  namespace           = "${var.project}/pipeline"
  metric_name         = "PipelineModelDrift"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_description = "A model's displayed win probabilities have drifted from reality on recent graded games (the 2025-26 calibrator-incident signature)."
  alarm_actions     = [aws_sns_topic.alerts.arn]
  ok_actions        = [aws_sns_topic.alerts.arn]
}


resource "aws_cloudwatch_metric_alarm" "pipeline_heartbeat" {
  alarm_name          = "${var.project}-pipeline-missed-run"
  namespace           = "${var.project}/pipeline"
  metric_name         = "PipelineHeartbeat"
  statistic           = "Sum"
  period              = 43200 # 12h
  evaluation_periods  = 2     # both halves of the day empty = missed run
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching" # NO log activity at all is exactly the bad case

  alarm_description = "Nightly predict heartbeat missing for a full day — the scheduled task didn't run or died before finishing."
  alarm_actions     = [aws_sns_topic.alerts.arn]
  ok_actions        = [aws_sns_topic.alerts.arn]
}
