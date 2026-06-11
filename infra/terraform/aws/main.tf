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

locals {
  common_tags = {
    Project = "dijkfood"
  }
}

resource "aws_ecr_repository" "repos" {
  for_each             = toset(var.ecr_repositories)
  name                 = "${var.ecr_repo_prefix}/${each.key}"
  image_tag_mutability = "MUTABLE"
  force_delete         = var.ecr_force_delete

  image_scanning_configuration {
    scan_on_push = var.ecr_scan_on_push
  }

  tags = local.common_tags
}

module "rds" {
  source = "./modules/rds"

  db_username = var.db_username
  db_password = var.db_password
  common_tags = local.common_tags
}

module "eks" {
  source = "./modules/eks"

  aws_region           = var.aws_region
  eks_cluster_name     = var.eks_cluster_name
  eks_cluster_role_arn = var.eks_cluster_role_arn
  eks_node_role_arn    = var.eks_node_role_arn
  common_tags          = local.common_tags
}

module "s3" {
  source = "./modules/s3"

  common_tags = local.common_tags
}

module "dynamodb" {
  source = "./modules/dynamodb"

  common_tags = local.common_tags
}

module "analytics" {
  source = "./modules/analytics"

  datalake_bucket_name = module.s3.datalake_bucket_name
  datalake_bucket_arn  = module.s3.datalake_bucket_arn
  common_tags          = local.common_tags
}

module "iot" {
  source = "./modules/iot"

  common_tags          = local.common_tags
}
