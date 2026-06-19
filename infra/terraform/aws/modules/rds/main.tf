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

resource "aws_db_parameter_group" "pg16" {
  name   = "dijkfood-pg16"
  family = "postgres16"

  # Optimize shared_buffers (25% of memory) - Static parameter
  parameter {
    name         = "shared_buffers"
    value        = "{DBInstanceClassMemory/32768}"
    apply_method = "pending-reboot"
  }

  # Optimize work_mem for faster query execution (64MB) - Dynamic parameter
  parameter {
    name  = "work_mem"
    value = "65536"
  }

  # Speed up write operations (commit returns before disk flush) - Dynamic parameter
  parameter {
    name  = "synchronous_commit"
    value = "off"
  }

  # Support larger connection pool sizes across replicas - Static parameter
  parameter {
    name         = "max_connections"
    value        = "1000"
    apply_method = "pending-reboot"
  }

  tags = var.common_tags
}

resource "aws_db_instance" "dijkfood" {
  for_each               = toset(var.db_instances)
  identifier             = "dijkfood-${each.key}"
  engine                 = "postgres"
  engine_version         = "16"
  instance_class         = "db.t3.medium"
  allocated_storage      = 20
  storage_type           = "gp3"
  db_name                = "dijkfood"
  username               = var.db_username
  password               = var.db_password
  parameter_group_name   = aws_db_parameter_group.pg16.name

  vpc_security_group_ids  = [aws_security_group.rds.id]
  publicly_accessible     = false
  skip_final_snapshot     = true
  backup_retention_period = 7

  tags = var.common_tags
}

output "rds_addresses" {
  value = { for k, v in aws_db_instance.dijkfood : k => v.address }
}
