variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "glue_role_arn" {
  type        = string
  description = "ARN do IAM Role que o Glue Job usará (precisa de acesso ao RDS, S3 e CloudWatch)"
}

variable "rds_jdbc_url" {
  type        = string
  description = "JDBC connection string do RDS: jdbc:postgresql://<host>:5432/dijkfood"
  sensitive   = true
}

variable "rds_username" {
  type      = string
  sensitive = true
}

variable "rds_password" {
  type      = string
  sensitive = true
}

variable "data_lake_bucket" {
  type        = string
  description = "Nome do bucket S3 onde o Glue vai escrever os dados (ex: dijkfood-data-lake)"
}

variable "scripts_bucket" {
  type        = string
  description = "Nome do bucket S3 onde ficam os scripts PySpark do Glue"
}

variable "glue_schedule" {
  type        = string
  description = "Cron expression para o trigger agendado (ex: cron(0 3 * * ? *) = 3h UTC diário)"
  default     = "cron(0 3 * * ? *)"
}

variable "glue_db_name" {
  type        = string
  description = "Nome do database no Glue Catalog"
  default     = "dijkfood_analytics"
}

variable "common_tags" {
  type    = map(string)
  default = {}
}
