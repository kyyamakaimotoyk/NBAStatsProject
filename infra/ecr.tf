#  private Docker registry in account so Fargate can pull the Week-1 container images. One repo per image → two repos: api and pipeline.
resource "aws_ecr_repository" "api" {
  name                 = "${var.project}-api"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = {
    Name = "${var.project}-api"
  }
}

resource "aws_ecr_repository" "pipeline" {
  name                 = "${var.project}-pipeline"
  image_tag_mutability = "MUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
  tags = {
    Name = "${var.project}-pipeline"
  }
}