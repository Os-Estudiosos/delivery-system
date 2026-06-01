terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "db_username" {}
variable "db_password" { sensitive = true }

resource "aws_db_instance" "dijkfood" {
  identifier        = "dijkfood"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = "db.t3.micro"
  allocated_storage = 20
  db_name           = "dijkfood"
  username          = var.db_username
  password          = var.db_password

  publicly_accessible     = false
  skip_final_snapshot     = false
  final_snapshot_identifier = "dijkfood-final"
  backup_retention_period = 7

  tags = {
    Project = "dijkfood"
  }
}
