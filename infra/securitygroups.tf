
# Ingress = the port I listen on, and who may reach it. Egress = where I'm allowed to reach out to.

resource "aws_security_group" "app" {
  vpc_id      = aws_vpc.main.id
  name        = "${var.project}-app"
  description = "Allow inbound and outbound traffic through internet gateway to get data from NBA_api, access models from S3 and serve data to RDS"
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"] # Allows traffic to everywhere
  }
  # No ingress because batch task is a client, not a server

  tags = {
    Name = "${var.project}-app"
  }
}


resource "aws_security_group" "rds" {
  vpc_id      = aws_vpc.main.id
  name        = "${var.project}-rds"
  description = "Direct packet traffic to and from RDS SQL database"

  # When the app connects in to RDS on 3306 (allowed by your
  #  ingress rule), the response traffic back to the app is automatically allowed — it does not need a matching egress rule. SGs track connection state: if a
  #  connection is allowed in, its replies are allowed out, period. Egress rules only govern connections RDS initiates on its own.

  # Keep note:  If you create a security group in the AWS console, AWS auto-adds a default "allow all outbound" egress rule. But the Terraform
  #  aws_security_group resource does NOT do that — if you leave out the egress block, Terraform actively manages egress as empty and strips that default. You'd
  #  end up with a SG that can make no outbound connections at all.
  egress { # not really required
    from_port   = 0
    to_port     = 0
    protocol    = -1
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id] # only the app tier has access to RDS
  }
  tags = {
    Name = "${var.project}-rds"
  }
}