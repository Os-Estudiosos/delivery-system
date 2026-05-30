variable "aws_region"          { default = "us-east-1" }
variable "aws_access_key_id"     {
                                default = ""
                                sensitive = true
                                }
variable "aws_secret_access_key" {
                                    default = ""
                                    sensitive = true
                                }
variable "aws_session_token"     {
                                    default = ""
                                    sensitive = true
                                }
variable "is_local"            { default = true }
variable "localstack_endpoint" { default = "http://localhost:4566" }
variable "k8s_context"         { default = "docker-desktop" }
variable "db_username"         { default = "" }
variable "db_password"         {
                                    default = ""
                                    sensitive = true
                                }