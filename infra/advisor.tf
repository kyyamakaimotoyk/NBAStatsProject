# =============================================================================
# Advisor service — the Bedrock-backed fantasy advisor as its OWN Fargate
# service with its OWN task role (zero-trust decision, player_projections_plan §5)
# =============================================================================
# Same container image as the API; the advisor router only mounts when
# ADVISOR_ENABLED=1, and only THIS task role carries bedrock:InvokeModel — the
# main API task keeps zero Bedrock permissions. Kill switch = scale this
# service to 0 (or set ADVISOR_DISABLED=1) without touching the API.
#
# Prerequisite (one-time, console): enable Anthropic model access in Bedrock
# for this account/region — see docs/bedrock_lab.md Lab 0.
# =============================================================================

resource "aws_cloudwatch_log_group" "advisor" {
  name              = "/ecs/${var.project}-advisor"
  retention_in_days = 14
}

resource "aws_iam_role" "advisor_task" {
  name               = "${var.project}-advisor-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# Rotation-aware DB secret read (same policy document as the API task role).
resource "aws_iam_role_policy" "advisor_task_secret" {
  name   = "${var.project}-advisor-task-secret"
  role   = aws_iam_role.advisor_task.id
  policy = data.aws_iam_policy_document.api_task_secret.json
}

# Bedrock, invoke-only. The Anthropic SDK's Mantle client (the Messages-API
# Bedrock endpoint) authorizes bedrock-mantle:CreateInference against a
# project resource — model-level scoping is not expressible there, so the
# model constraint is enforced by BEDROCK_MODEL_ID in the task env. The
# classic bedrock:InvokeModel statement stays for the legacy runtime surface.
data "aws_iam_policy_document" "advisor_bedrock" {
  statement {
    sid       = "MantleInference"
    actions   = ["bedrock-mantle:CreateInference"]
    resources = ["arn:aws:bedrock-mantle:*:${data.aws_caller_identity.current.account_id}:project/default"]
  }

  statement {
    sid = "InvokeSonnetOnly"
    actions = [
      "bedrock:InvokeModel",
      "bedrock:InvokeModelWithResponseStream",
    ]
    resources = [
      # Sonnet 4.6 (current, via us.* inference profile) + Sonnet 5 (kept for
      # the flip-back once the entitlement bug is resolved).
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-4-6*",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*.anthropic.claude-sonnet-4-6*",
      "arn:aws:bedrock:*::foundation-model/anthropic.claude-sonnet-5*",
      "arn:aws:bedrock:*:${data.aws_caller_identity.current.account_id}:inference-profile/*.anthropic.claude-sonnet-5*",
    ]
  }
}

resource "aws_iam_role_policy" "advisor_bedrock" {
  name   = "${var.project}-advisor-bedrock"
  role   = aws_iam_role.advisor_task.id
  policy = data.aws_iam_policy_document.advisor_bedrock.json
}

# Write-only access to the analysis prefix in the logs bucket — nothing else.
data "aws_iam_policy_document" "advisor_s3_archive" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${aws_s3_bucket.logs.arn}/advisor_inputs/*"]
  }
}

resource "aws_iam_role_policy" "advisor_s3_archive" {
  name   = "${var.project}-advisor-s3-archive"
  role   = aws_iam_role.advisor_task.id
  policy = data.aws_iam_policy_document.advisor_s3_archive.json
}

# Turnstile secret read — only created once the secret exists.
resource "aws_iam_role_policy" "advisor_turnstile_secret" {
  count = var.turnstile_secret_arn == "" ? 0 : 1
  name  = "${var.project}-advisor-turnstile"
  role  = aws_iam_role.advisor_task.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [var.turnstile_secret_arn]
    }]
  })
}

# -----------------------------------------------------------------------------
# Spend observability: near-real-time token alarm + monthly Bedrock budget
# -----------------------------------------------------------------------------
# The advisor prints "ADVISOR_TOKENS <in> <out>" (bare numbers on purpose —
# classic metric filters can extract a field but not parse key=value pairs).
resource "aws_cloudwatch_log_metric_filter" "advisor_tokens" {
  name           = "${var.project}-advisor-tokens"
  log_group_name = aws_cloudwatch_log_group.advisor.name
  pattern        = "[label=ADVISOR_TOKENS, tin, tout]"

  metric_transformation {
    name          = "AdvisorInputTokens"
    namespace     = "${var.project}/advisor"
    value         = "$tin"
    default_value = "0"
  }
}

# ~2M input tokens/day is roughly $4/day at Sonnet intro pricing — far above
# legitimate hobby traffic, early enough to stop a farming burst same-day.
resource "aws_cloudwatch_metric_alarm" "advisor_tokens" {
  alarm_name          = "${var.project}-advisor-token-burn"
  namespace           = "${var.project}/advisor"
  metric_name         = "AdvisorInputTokens"
  statistic           = "Sum"
  period              = 86400
  evaluation_periods  = 1
  threshold           = 2000000
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"

  alarm_description = "Advisor consumed >2M Bedrock input tokens in a day — possible farming; consider ADVISOR_DISABLED=1 or scaling the service to 0."
  alarm_actions     = [aws_sns_topic.alerts.arn]
  ok_actions        = [aws_sns_topic.alerts.arn]
}

# Money backstop (Budgets lags ~8-24h; the token alarm above is the fast path).
resource "aws_budgets_budget" "bedrock" {
  name         = "${var.project}-bedrock-monthly"
  budget_type  = "COST"
  limit_amount = "10"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  cost_filter {
    name   = "Service"
    values = ["Amazon Bedrock"]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.alert_email]
  }
}

resource "aws_ecs_task_definition" "advisor" {
  family                   = "${var.project}-advisor"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.advisor_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "advisor"
      image     = "${aws_ecr_repository.api.repository_url}:latest"
      essential = true
      portMappings = [
        { containerPort = 8000, protocol = "tcp" }
      ]
      environment = [
        { name = "NBA_DB_HOST", value = aws_db_instance.main.address },
        { name = "NBA_DB_PORT", value = tostring(aws_db_instance.main.port) },
        { name = "NBA_DB_USER", value = var.db_username },
        { name = "NBA_DB_NAME", value = var.db_name },
        { name = "ALLOWED_ORIGINS", value = "https://${var.domain_name},https://www.${var.domain_name}" },
        { name = "NBA_DB_SECRET_ARN", value = aws_db_instance.main.master_user_secret[0].secret_arn },
        # Advisor-specific:
        { name = "ADVISOR_ENABLED", value = "1" },
        { name = "AWS_REGION_NAME", value = var.aws_region },
        # Sonnet 4.6 via inference profile, NOT Sonnet 5: the newest-gen models
        # are blocked by a known Bedrock entitlement-sync bug (2026-07-13,
        # "not available for this account" despite AUTHORIZED). Flip back to
        # anthropic.claude-sonnet-5 + the Mantle client when AWS fixes it.
        { name = "BEDROCK_MODEL_ID", value = "us.anthropic.claude-sonnet-4-6" },
        { name = "ADVISOR_DAILY_CAP", value = "300" },     # global requests/day
        { name = "ADVISOR_IP_DAILY_CAP", value = "20" },   # per-IP requests/day
        { name = "ADVISOR_MAX_CONCURRENCY", value = "4" }, # global in-flight ceiling
        { name = "ADVISOR_MAX_TOKENS", value = "800" },    # per-response output cap
        # Analysis corpus: one JSON record per request under advisor_inputs/
        # (hashed IP only; 180-day lifecycle; Athena table in analytics.tf).
        { name = "ADVISOR_LOG_BUCKET", value = aws_s3_bucket.logs.bucket },
        # Cloudflare Turnstile: empty = verification disabled. Set to a
        # Secrets Manager ARN (create the secret yourself in a terminal).
        { name = "TURNSTILE_SECRET_ARN", value = var.turnstile_secret_arn },
      ]
      secrets = [
        {
          name      = "NBA_DB_PASSWORD"
          valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::"
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.advisor.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "advisor"
        }
      }
    }
  ])
}

resource "aws_lb_target_group" "advisor" {
  name        = "${var.project}-advisor-tg"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id

  health_check {
    path                = "/api/health"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  deregistration_delay = 15
}

# Path routing: only /api/advisor* reaches the Bedrock-capable service.
resource "aws_lb_listener_rule" "advisor" {
  listener_arn = aws_lb_listener.https.arn
  priority     = 10

  action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.advisor.arn
  }

  condition {
    path_pattern {
      values = ["/api/advisor*"]
    }
  }
}

resource "aws_ecs_service" "advisor" {
  name            = "${var.project}-advisor"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.advisor.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  # Same as the api service: propagate tags so Fargate spend is cost-allocated.
  enable_ecs_managed_tags = true
  propagate_tags          = "SERVICE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.app.id, aws_security_group.api.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.advisor.arn
    container_name   = "advisor"
    container_port   = 8000
  }

  health_check_grace_period_seconds = 60

  depends_on = [aws_lb_listener.https]
}
