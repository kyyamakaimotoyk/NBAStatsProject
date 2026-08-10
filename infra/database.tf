
resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db-subnets"
  subnet_ids = aws_subnet.private[*].id
  tags = {
    Name = "${var.project}-db-subnets"
  }
}

resource "aws_db_instance" "main" {
  identifier                  = "${var.project}-db"
  engine                      = "mysql"
  engine_version              = "8.4"
  allow_major_version_upgrade = true
  instance_class              = var.db_instance_class
  allocated_storage           = 20
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = var.db_name
  username                    = var.db_username
  manage_master_user_password = true
  db_subnet_group_name        = aws_db_subnet_group.main.name
  vpc_security_group_ids      = [aws_security_group.rds.id]
  multi_az                    = false
  publicly_accessible         = false
  backup_retention_period     = 7
  skip_final_snapshot         = true
  deletion_protection         = false
  apply_immediately           = true
  tags = {
    Name = "${var.project}-db-instance"
  }
}