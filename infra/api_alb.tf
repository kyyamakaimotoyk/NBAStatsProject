# =============================================================================
# Application Load Balancer for the API service (Week 3.3)
# =============================================================================
# Why an ALB: a bare Fargate task only gets a public IP that changes on every
# restart — no good for something a browser reaches by name. The ALB is a stable,
# managed front door that:
#   - has a fixed DNS name (we alias api.hoopmodel.com to it),
#   - terminates HTTPS with the ACM cert (encryption + the padlock),
#   - health-checks the task and only sends traffic to healthy ones,
#   - lets the API task itself stay private (only the ALB may reach :8000).
#
# Request path:
#   viewer ──HTTPS──> CloudFront ──HTTPS:443──> ALB ──HTTP:8000──> API task
# CloudFront is the public front line (DDoS edge absorption, WAF-ready, origin
# hiding); this ALB only accepts connections from CloudFront's IP ranges.
# =============================================================================


# -----------------------------------------------------------------------------
# ALB security group — public on 443/80, the only thing the internet talks to
# -----------------------------------------------------------------------------
resource "aws_security_group" "alb" {
  vpc_id      = aws_vpc.main.id
  name        = "${var.project}-alb"
  description = "ALB is the API CloudFront origin; only CloudFront edge IPs may reach :443"

  # The ALB is NOT directly public. Only CloudFront's edge servers may connect, via
  # the AWS-managed prefix list of CloudFront origin-facing IP ranges (kept current
  # by AWS). The open internet hits CloudFront, never the ALB.
  ingress {
    description     = "HTTPS from CloudFront edge servers only"
    from_port       = 443
    to_port         = 443
    protocol        = "tcp"
    prefix_list_ids = [data.aws_ec2_managed_prefix_list.cloudfront.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project}-alb"
  }
}


# -----------------------------------------------------------------------------
# The load balancer — internet-facing, spread across both public subnets
# -----------------------------------------------------------------------------
resource "aws_lb" "main" {
  name               = "${var.project}-alb"
  load_balancer_type = "application"
  internal           = false
  security_groups    = [aws_security_group.alb.id]
  subnets            = aws_subnet.public[*].id
}


# -----------------------------------------------------------------------------
# Target group — the pool of backends the ALB forwards to + how it health-checks
# -----------------------------------------------------------------------------
# target_type = "ip" because Fargate (awsvpc) tasks are addressed by IP, not by
# EC2 instance id. The ECS service registers its task IPs here automatically.
resource "aws_lb_target_group" "api" {
  name        = "${var.project}-api-tg"
  port        = 8000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = aws_vpc.main.id

  health_check {
    path                = "/api/health" # returns 200 whenever the process is up
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }

  # Give a draining task a few seconds to finish in-flight requests on deploy.
  deregistration_delay = 15
}


# -----------------------------------------------------------------------------
# Listeners — what the ALB does with traffic on each port
# -----------------------------------------------------------------------------
# HTTPS:443 — terminate TLS with the ACM cert, forward to the API target group.
resource "aws_lb_listener" "https" {
  load_balancer_arn = aws_lb.main.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.main.certificate_arn

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# No HTTP:80 listener — CloudFront terminates the viewer connection and does the
# HTTP->HTTPS redirect at the edge, then reaches this ALB on 443 only.
#
# DNS lives in api_cloudfront.tf now:
#   api.hoopmodel.com         -> CloudFront (the public name)
#   api-origin.hoopmodel.com  -> this ALB    (CloudFront's origin; covered by the
#                                             wildcard cert so the HTTPS origin leg
#                                             validates)
