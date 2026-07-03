# =============================================================================
# API service — the FastAPI "serve" tier as an always-on Fargate service (3.1)
# =============================================================================
# Difference from the pipeline (ecs.tf): the pipeline is a *one-off task* we
# launch by hand and it exits. The API is a long-lived SERVER, so it runs as an
# ECS *service* — ECS keeps `desired_count` copies alive and restarts any that
# crash. Same cluster, same execution role + DB secret; new task def, new SG,
# new log group.
#
# 3.1 scope: reachable directly on the task's public IP, HTTP :8000, RDS-backed.
# In 3.3 an ALB goes in front (stable HTTPS) and we tighten the SG so only the
# ALB can hit :8000.
# =============================================================================


# -----------------------------------------------------------------------------
# Security group — inbound 8000 (the API is a SERVER, unlike the egress-only app SG)
# -----------------------------------------------------------------------------
# For 3.1 we open 8000 to the internet so we can curl the task's public IP and
# prove it serves. In 3.3 this ingress changes to "from the ALB SG only".
resource "aws_security_group" "api" {
  vpc_id      = aws_vpc.main.id
  name        = "${var.project}-api"
  description = "Public API tier: inbound 8000 (temporary 0.0.0.0/0 until ALB fronts it)"

  ingress {
    description     = "FastAPI/uvicorn HTTP - only the ALB may reach the tasks now"
    from_port       = 8000
    to_port         = 8000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project}-api"
  }
}


# -----------------------------------------------------------------------------
# CloudWatch log group for the API container
# -----------------------------------------------------------------------------
resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${var.project}-api"
  retention_in_days = 14
}


# -----------------------------------------------------------------------------
# API task role — lets the app RE-READ the rotating DB secret at runtime
# -----------------------------------------------------------------------------
# The execution role's secret read only happens once, at task LAUNCH (the
# `secrets` env injection). The weekly password rotation therefore stranded
# long-lived tasks with a stale password (2026-06-29 / 2026-07-03 incidents).
# api/db.py now fetches the secret itself on new connections and refreshes on
# auth failure — which needs the TASK role (the app's own identity) to read it.
resource "aws_iam_role" "api_task" {
  name               = "${var.project}-api-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

data "aws_iam_policy_document" "api_task_secret" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_db_instance.main.master_user_secret[0].secret_arn]
  }
}

resource "aws_iam_role_policy" "api_task_secret" {
  name   = "${var.project}-api-task-secret"
  role   = aws_iam_role.api_task.id
  policy = data.aws_iam_policy_document.api_task_secret.json
}


# -----------------------------------------------------------------------------
# Task definition — one small uvicorn container (0.25 vCPU / 0.5 GB)
# -----------------------------------------------------------------------------
# Reuses aws_iam_role.ecs_execution from ecs.tf (ECR pull + logs + secret read).
resource "aws_ecs_task_definition" "api" {
  family                   = "${var.project}-api"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256" # 0.25 vCPU
  memory                   = "512" # 0.5 GB
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.api_task.arn

  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  container_definitions = jsonencode([
    {
      name      = "api"
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
        # CORS allow-list for the production site (browser enforces this on the
        # cross-origin fetch from hoopmodel.com to api.hoopmodel.com).
        { name = "ALLOWED_ORIGINS", value = "https://${var.domain_name},https://www.${var.domain_name}" },
        # Rotation-aware DB auth: api/db.py fetches the password from this
        # secret on new connections and re-fetches on auth failure, so the
        # weekly rotation no longer strands a long-lived task.
        { name = "NBA_DB_SECRET_ARN", value = aws_db_instance.main.master_user_secret[0].secret_arn },
      ]
      # Launch-time injection kept as a fallback (and for any old image without
      # the rotation-aware connector). api/db.py prefers NBA_DB_SECRET_ARN.
      secrets = [
        {
          name      = "NBA_DB_PASSWORD"
          valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::"
        },
      ]
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.api.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "api"
        }
      }
    }
  ])
}


# -----------------------------------------------------------------------------
# ECS service — keep 1 task alive, in a public subnet with a public IP
# -----------------------------------------------------------------------------
# Two SGs on the task:
#   - app SG  -> egress to reach RDS (the rds SG already trusts the app SG on 3306)
#   - api SG  -> inbound 8000 so we can reach the API
# assign_public_ip = true because there's no NAT; the task needs a public IP to
# pull its image and reach AWS APIs (and, in 3.1, to be reachable for testing).
resource "aws_ecs_service" "api" {
  name            = "${var.project}-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.app.id, aws_security_group.api.id]
    assign_public_ip = true
  }

  # Register each task's IP into the ALB target group on the API container's port.
  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  # Don't mark a freshly-started task unhealthy while uvicorn is still booting.
  health_check_grace_period_seconds = 60

  # The ALB listener must exist before the service can register targets into it.
  depends_on = [aws_lb_listener.https]
}
