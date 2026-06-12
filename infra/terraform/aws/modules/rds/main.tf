data "aws_vpc" "default" {
  default = true
}

resource "aws_security_group" "rds" {
  name        = "dijkfood-rds-sg"
  description = "Allow inbound traffic to RDS from VPC"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "PostgreSQL access from VPC"
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [data.aws_vpc.default.cidr_block]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = var.common_tags
}

resource "aws_db_instance" "dijkfood" {
  identifier        = "dijkfood"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  db_name           = "dijkfood"
  username          = var.db_username
  password          = var.db_password

  vpc_security_group_ids  = [aws_security_group.rds.id]
  publicly_accessible     = false
  skip_final_snapshot     = true
  backup_retention_period = 7

  tags = var.common_tags
}

output "rds_address" {
  value = aws_db_instance.dijkfood.address
}
