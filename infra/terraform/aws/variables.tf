variable "aws_region" {
  default = "us-east-1"
}

variable "aws_access_key_id" {
  default = ""
}

variable "aws_secret_access_key" {
  default   = ""
  sensitive = true
}

variable "aws_session_token" {
  default   = ""
  sensitive = true
}

variable "db_username" {
  default = "dijkfood"
}

variable "db_password" {
  sensitive = true
}

variable "eks_cluster_name" {
  default = "dijkfood"
}
