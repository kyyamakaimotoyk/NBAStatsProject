# =============================================================================
# Nightly predict schedule (Week 4.1)
# =============================================================================
# EventBridge Scheduler runs the pipeline image's default command
# (batch_predict_today.py) as a one-off Fargate task on a cron. No command
# override is needed — the pipeline task definition's CMD already predicts today.
#
# Reuses everything from Week 2.5: the same pipeline task definition (pulls models
# from S3, schedule from the CDN, writes to model_predictions), in the public
# subnets with the app SG (egress to RDS + internet). Only NEW thing here: a role
# the scheduler assumes to call ecs:RunTask + pass the task's IAM roles.
#
# Offseason note: this finds "no games" all summer (harmless, ~$0.004/run) and
# starts producing the moment the season tips off. Flip `state` to "DISABLED" to
# pause it over the summer if you'd rather not pay the pennies.
# =============================================================================


# -----------------------------------------------------------------------------
# Role the scheduler assumes to launch the task
# -----------------------------------------------------------------------------
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.project}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

# It may run the pipeline task, and pass the two task IAM roles to ECS (RunTask
# hands the execution + task roles to the launched task — that's iam:PassRole).
data "aws_iam_policy_document" "scheduler_run" {
  statement {
    sid       = "RunTask"
    actions   = ["ecs:RunTask"]
    resources = [aws_ecs_task_definition.pipeline.arn]
  }

  statement {
    sid       = "PassRoles"
    actions   = ["iam:PassRole"]
    resources = [aws_iam_role.ecs_execution.arn, aws_iam_role.ecs_task.arn]
    condition {
      test     = "StringLike"
      variable = "iam:PassedToService"
      values   = ["ecs-tasks.amazonaws.com"]
    }
  }

  # Roll the API service (the daily-restart schedule below). force-new-deployment
  # doesn't change the task def, so no PassRole is needed here.
  statement {
    sid       = "RestartApiService"
    actions   = ["ecs:UpdateService"]
    resources = [aws_ecs_service.api.id]
  }
}

resource "aws_iam_role_policy" "scheduler_run" {
  name   = "${var.project}-scheduler-run"
  role   = aws_iam_role.scheduler.id
  policy = data.aws_iam_policy_document.scheduler_run.json
}


# -----------------------------------------------------------------------------
# The schedule
# -----------------------------------------------------------------------------
resource "aws_scheduler_schedule" "nightly_predict" {
  name  = "${var.project}-nightly-predict"
  state = "ENABLED"

  # Run once a day at 11:00 AM US Eastern. Tunable: earlier = predictions on the
  # site sooner; later = firmer injury data (the job fetches live injuries for
  # today). cron fields: (minute hour day-of-month month day-of-week year).
  schedule_expression          = "cron(0 11 * * ? *)"
  schedule_expression_timezone = "America/New_York"

  # Run exactly at the time, no jitter window.
  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.pipeline.arn
      launch_type         = "FARGATE"
      task_count          = 1

      network_configuration {
        subnets          = aws_subnet.public[*].id
        security_groups  = [aws_security_group.app.id]
        assign_public_ip = true # no NAT; the task needs a public IP for ECR/S3/CDN
      }
    }

    # If a launch fails transiently, retry for up to an hour.
    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
  }
}


# =============================================================================
# Weekly retrain (added 2026-07-04) — features -> train -> validate, cloud-side
# =============================================================================
# Monday 13:00 ET, after the weekend slates are graded. All stages are DB-only
# (post-egress-fix): compute_elo refreshes team_elo_pregame from game_list,
# player_impact + features + train + validate run through the pipeline runner.
# Train records feature_set_version lineage (E19+) and pushes fresh bundles to
# the S3 artifact store, so prod models and calibrators are never more than a
# week stale — the E21-identified root cause of the calibration incident.
# The `input` block overrides the container command (the task def's default CMD
# is the nightly predictor).
#
# Offseason note: retraining on unchanged data reproduces near-identical models
# (fixed seeds) — harmless. Review the first few runs' [E20] calibrator-shift
# NOTE lines and validate output in the logs.
resource "aws_scheduler_schedule" "weekly_retrain" {
  name  = "${var.project}-weekly-retrain"
  state = "ENABLED"

  schedule_expression          = "cron(0 13 ? * MON *)"
  schedule_expression_timezone = "America/New_York"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = aws_ecs_cluster.main.arn
    role_arn = aws_iam_role.scheduler.arn

    ecs_parameters {
      task_definition_arn = aws_ecs_task_definition.pipeline.arn
      launch_type         = "FARGATE"
      task_count          = 1

      network_configuration {
        subnets          = aws_subnet.public[*].id
        security_groups  = [aws_security_group.app.id]
        assign_public_ip = true
      }
    }

    input = jsonencode({
      containerOverrides = [
        {
          name = "pipeline"
          command = ["sh", "-c",
            "python data_engineering/compute_elo.py && python orchestration/pipeline.py run --stages player_impact,features,train,player_train,validate"]
        }
      ]
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
  }
}


# =============================================================================
# Daily API restart — keeps the injected DB password fresh (added 2026-06-29)
# =============================================================================
# WHY: the RDS master password auto-rotates (~weekly via Secrets Manager). The
# API task injects that password as an env var AT LAUNCH and freezes it. Once the
# password rotates, a still-running task holds the stale one -> "Access denied" ->
# the whole site shows "Failed to fetch". A daily forced redeployment guarantees
# the running task is never more than ~1 day old, so it always re-reads a current
# password (weekly rotation << daily restart). See docs/troubleshooting_lab.md.
#
# This uses an EventBridge Scheduler UNIVERSAL TARGET: instead of launching a
# task, it calls the ECS UpdateService API directly (forceNewDeployment=true),
# which rolls the service in place. Input keys are PascalCase (universal-target
# convention), not the API's native camelCase.
resource "aws_scheduler_schedule" "api_daily_restart" {
  name  = "${var.project}-api-daily-restart"
  state = "ENABLED"

  # 4:00 AM US Eastern — low-traffic window; rolling deploy is near-zero downtime
  # anyway (ALB drains the old task as the new one passes health checks).
  schedule_expression          = "cron(0 4 * * ? *)"
  schedule_expression_timezone = "America/New_York"

  flexible_time_window {
    mode = "OFF"
  }

  target {
    arn      = "arn:aws:scheduler:::aws-sdk:ecs:updateService"
    role_arn = aws_iam_role.scheduler.arn

    input = jsonencode({
      Cluster            = aws_ecs_cluster.main.arn
      Service            = aws_ecs_service.api.name
      ForceNewDeployment = true
    })

    retry_policy {
      maximum_event_age_in_seconds = 3600
      maximum_retry_attempts       = 3
    }
  }
}
