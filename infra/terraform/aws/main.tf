terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region     = var.aws_region
  access_key = var.aws_access_key_id
  secret_key = var.aws_secret_access_key
  token      = var.aws_session_token
}

module "sqs" {
  source = "./modules/sqs"
}

module "dynamodb" {
  source = "./modules/dynamodb"
}

module "s3" {
  source = "./modules/s3"
}

module "rds" {
  source      = "./modules/rds"
  db_username = var.db_username
  db_password = var.db_password
}

module "eks" {
  source       = "./modules/eks"
  cluster_name = var.eks_cluster_name
}
