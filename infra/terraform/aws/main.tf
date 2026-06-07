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

  # nomes dos buckets centralizados aqui para evitar repetição
  data_lake_bucket      = "dijkfood-data-lake"
  athena_results_bucket = "dijkfood-athena-results"
}

# ── Módulos existentes ────────────────────────────────────────────────────────
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

module "sqs" {
  source = "./modules/sqs"
}

# ── Camada analítica ──────────────────────────────────────────────────────────
module "s3_data_lake" {
  source = "./modules/s3_data_lake"

  data_lake_bucket = local.data_lake_bucket
  common_tags      = local.common_tags
}

module "glue" {
  source = "./modules/glue"

  aws_region       = var.aws_region
  glue_role_arn    = var.glue_role_arn
  rds_jdbc_url     = "jdbc:postgresql://${module.rds.db_endpoint}/dijkfood"
  rds_username     = var.db_username
  rds_password     = var.db_password
  data_lake_bucket = local.data_lake_bucket
  scripts_bucket   = local.data_lake_bucket
  glue_schedule    = var.glue_schedule
  glue_db_name     = var.glue_db_name
  common_tags      = local.common_tags

  depends_on = [module.s3_data_lake]
}

module "athena" {
  source = "./modules/athena"

  data_lake_bucket      = local.data_lake_bucket
  athena_results_bucket = local.athena_results_bucket
  glue_db_name          = var.glue_db_name
  workgroup_name        = var.athena_workgroup_name
  bytes_scanned_limit   = var.athena_bytes_scanned_limit
  common_tags           = local.common_tags

  depends_on = [module.glue]
}

# ── Outputs úteis pós-apply ───────────────────────────────────────────────────
output "data_lake_bucket" {
  value = module.s3_data_lake.data_lake_bucket
}

output "glue_job_name" {
  value = module.glue.glue_job_name
}

output "glue_crawler_name" {
  value = module.glue.glue_crawler_name
}

output "athena_workgroup" {
  value = module.athena.workgroup_name
}

output "athena_results_bucket" {
  value = module.athena.athena_results_bucket
}

module "ec2" {
  source = "./modules/ec2"

  aws_region           = var.aws_region
  instance_type        = "t3.micro"
  athena_db            = var.glue_db_name
  athena_workgroup     = var.athena_workgroup_name
  results_bucket       = local.athena_results_bucket
  data_lake_bucket     = local.data_lake_bucket
  ec2_instance_profile = var.ec2_instance_profile
  common_tags          = local.common_tags

  depends_on = [module.athena, module.s3_data_lake]
}

output "dashboard_url" {
  value = module.ec2.dashboard_url
}
