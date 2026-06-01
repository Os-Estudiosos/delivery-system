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
  skip_final_snapshot     = true
  backup_retention_period = 7

  tags = var.common_tags
}
