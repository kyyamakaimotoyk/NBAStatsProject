# =============================================================================
# ECS / Fargate — runs the pipeline container in the cloud (Week 2.5)
# =============================================================================
# Mental model: ECS is the "what to run + where to run it" layer.
#
#   - Cluster              = a namespace the tasks live in. With Fargate there are
#                            NO servers to manage; the cluster is just a logical
#                            grouping + a place CloudWatch metrics attach to.
#   - Task definition      = the blueprint for ONE running container: which image,
#                            how much CPU/RAM, the command, env vars, secrets, and
#                            where logs go. Think of it as a versioned recipe.
#   - Task                 = one running instance of that blueprint. We launch it
#                            on demand with `aws ecs run-task` (2.5c). Later
#                            (Week 4) EventBridge will launch it on a schedule.
#   - Two IAM roles        = WHO is allowed to do WHAT:
#       * execution role  -> used by the ECS *agent* (AWS's machinery) to pull the
#                            image from ECR, write logs, and fetch the DB password
#                            secret so it can inject it into the container.
#       * task role       -> used by *your code* inside the container (boto3) to
#                            reach S3 and download the model bundles.
#     They are separate on purpose: the agent's permissions and your app's
#     permissions are different blast radii. Least privilege.
# =============================================================================


# -----------------------------------------------------------------------------
# 1. Cluster — the (serverless) home for Fargate tasks
# -----------------------------------------------------------------------------
resource "aws_ecs_cluster" "main" {
  name = "${var.project}-cluster"
}


# -----------------------------------------------------------------------------
# 2. CloudWatch log group — where the container's stdout/stderr lands
# -----------------------------------------------------------------------------
# Fargate's awslogs driver streams everything the container prints to here. This
# is how you'll SEE whether the pipeline connected to RDS, loaded models from S3,
# and wrote predictions — there's no SSH into a Fargate task, logs are the window.
resource "aws_cloudwatch_log_group" "pipeline" {
  name              = "/ecs/${var.project}-pipeline"
  retention_in_days = 14 # auto-delete logs older than 14 days (keeps costs ~0)
}


# -----------------------------------------------------------------------------
# 3a. Trust policy shared by both roles
# -----------------------------------------------------------------------------
# An IAM role isn't a user — it's a set of permissions that some PRINCIPAL is
# allowed to "assume". This trust policy says: the ECS-tasks service is allowed
# to assume these roles. Without it, AWS would refuse to hand the role to a task.
data "aws_iam_policy_document" "ecs_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}


# -----------------------------------------------------------------------------
# 3b. Execution role — the ECS agent's permissions (pull image, logs, secret)
# -----------------------------------------------------------------------------
resource "aws_iam_role" "ecs_execution" {
  name               = "${var.project}-ecs-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# AWS's canned policy that grants exactly "pull from ECR + write to CloudWatch
# Logs". This is the standard execution-role baseline; we don't hand-roll it.
resource "aws_iam_role_policy_attachment" "ecs_execution_managed" {
  role       = aws_iam_role.ecs_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Extra grant: let the agent READ the RDS-managed secret so it can inject the
# password into the container as NBA_DB_PASSWORD. The `secrets` block in the task
# definition (below) is fetched by the EXECUTION role, not the task role — a
# common gotcha. We scope it to exactly this one secret ARN, nothing else.
data "aws_iam_policy_document" "ecs_execution_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [aws_db_instance.main.master_user_secret[0].secret_arn]
  }
}
resource "aws_iam_role_policy" "ecs_execution_secrets" {
  name   = "${var.project}-ecs-execution-secrets"
  role   = aws_iam_role.ecs_execution.id
  policy = data.aws_iam_policy_document.ecs_execution_secrets.json
}


# -----------------------------------------------------------------------------
# 3c. Task role — your code's permissions (read models from S3)
# -----------------------------------------------------------------------------
resource "aws_iam_role" "ecs_task" {
  name               = "${var.project}-ecs-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_assume.json
}

# The container's boto3 (artifact_store.S3Store) needs to LIST the bucket and GET
# objects to pull model bundles. ListBucket is granted on the bucket ARN itself;
# GetObject on the objects inside it (the "/*"). Read-only — a predictor never
# writes models.
data "aws_iam_policy_document" "ecs_task_s3" {
  statement {
    actions = ["s3:GetObject", "s3:ListBucket"]
    resources = [
      aws_s3_bucket.models.arn,
      "${aws_s3_bucket.models.arn}/*",
    ]
  }
}
resource "aws_iam_role_policy" "ecs_task_s3" {
  name   = "${var.project}-ecs-task-s3"
  role   = aws_iam_role.ecs_task.id
  policy = data.aws_iam_policy_document.ecs_task_s3.json
}


# -----------------------------------------------------------------------------
# 4. Task definition — the blueprint for one pipeline container
# -----------------------------------------------------------------------------
resource "aws_ecs_task_definition" "pipeline" {
  family                   = "${var.project}-pipeline"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc" # required for Fargate; each task gets its own ENI
  cpu                      = "2048"   # 2 vCPU  )  must be a valid Fargate CPU/mem
  memory                   = "8192"   # 8 GB    )  pair; torch + pandas like headroom
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  # The image was built on Docker Desktop (Windows) which produces linux/amd64.
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "X86_64"
  }

  # container_definitions is AWS's native JSON; jsonencode lets us write it as an
  # HCL object and have Terraform serialize it. One container named "pipeline".
  container_definitions = jsonencode([
    {
      name      = "pipeline"
      image     = "${aws_ecr_repository.pipeline.repository_url}:latest"
      essential = true

      # Plaintext, non-secret config. Note the DB host/port come straight from the
      # RDS resource's computed attributes — no copy-paste, always correct.
      environment = [
        { name = "NBA_DB_HOST", value = aws_db_instance.main.address },
        { name = "NBA_DB_PORT", value = tostring(aws_db_instance.main.port) },
        { name = "NBA_DB_USER", value = var.db_username },
        { name = "NBA_DB_NAME", value = var.db_name },
        { name = "MODELS_S3_BUCKET", value = aws_s3_bucket.models.bucket },
      ]

      # Secret value injected at launch. The ":password::" suffix tells ECS to pull
      # just the `password` JSON key out of the RDS secret (which holds
      # {"username":...,"password":...}). The container sees a normal env var; the
      # value never appears in the task definition or logs.
      secrets = [
        {
          name      = "NBA_DB_PASSWORD"
          valueFrom = "${aws_db_instance.main.master_user_secret[0].secret_arn}:password::"
        },
      ]

      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.pipeline.name
          "awslogs-region"        = var.aws_region
          "awslogs-stream-prefix" = "pipeline"
        }
      }
    }
  ])
}
