terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    docker = {
      source  = "kreuzwerker/docker"
      version = "~> 3.0"
    }
    kubectl = {
      source  = "gavinbunney/kubectl"
      version = "~> 1.14"
    }
  }
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = var.aws_access_key
  secret_key                  = var.aws_secret_key
  skip_credentials_validation = var.is_local
  skip_metadata_api_check     = var.is_local
  skip_requesting_account_id  = var.is_local

  s3_use_path_style = true

  dynamic "endpoints" {
    for_each = var.is_local ? [1] : []
    content {
      sqs      = var.localstack_endpoint
      dynamodb = var.localstack_endpoint
      s3       = var.localstack_endpoint
    }
  }
}

provider "docker" {}

provider "kubernetes" {
  config_path    = "~/.kube/config"
  config_context = var.k8s_context
}

provider "kubectl" {
  config_path    = "~/.kube/config"
  config_context = var.k8s_context
}

module "containers" {
  count  = var.is_local ? 1 : 0
  source = "./modules/containers"
}

module "sqs" {
  source     = "./modules/sqs"
  depends_on = [module.containers]
}

module "dynamodb" {
  source     = "./modules/dynamodb"
  depends_on = [module.containers]
}

module "s3" {
  source     = "./modules/s3"
  is_local   = var.is_local
  depends_on = [module.containers]
}

module "rds" {
  count  = var.is_local ? 0 : 1
  source = "./modules/rds"

  db_username = var.db_username
  db_password = var.db_password
}

module "kubernetes" {
  source   = "./modules/kubernetes"
  k8s_path = "${path.root}/../k8s"
}