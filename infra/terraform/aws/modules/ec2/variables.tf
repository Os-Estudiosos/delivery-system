variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "instance_type" {
  type    = string
  default = "t3.micro"
}

variable "athena_db" {
  type    = string
  default = "dijkfood_analytics"
}

variable "athena_workgroup" {
  type    = string
  default = "dijkfood-analytics"
}

variable "results_bucket" {
  type        = string
  description = "Bucket S3 dos resultados do Athena"
}

variable "data_lake_bucket" {
  type        = string
  description = "Bucket S3 do data lake (leitura pelo Athena)"
}

variable "ec2_instance_profile" {
  type        = string
  description = "Nome do IAM Instance Profile com permissões Athena + S3 (ex: LabInstanceProfile)"
  default     = "LabInstanceProfile"
}

variable "dashboard_s3_key" {
  type        = string
  description = "Chave S3 do dashboard_prod.py no data lake"
  default     = "glue-scripts/dashboard_prod.py"
}

variable "common_tags" {
  type    = map(string)
  default = {}
}
