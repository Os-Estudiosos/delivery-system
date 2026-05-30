variable "aws_region"          { default = "us-east-1" }
variable "aws_access_key"      { default = "test" }
variable "aws_secret_key"      { default = "test" }
variable "is_local"            { default = true }
variable "localstack_endpoint" { default = "http://localhost:4566" }
variable "k8s_context"         { default = "docker-desktop" }
variable "db_username"         { default = "" }
variable "db_password"         {
                                    default = ""
                                    sensitive = true
                                }