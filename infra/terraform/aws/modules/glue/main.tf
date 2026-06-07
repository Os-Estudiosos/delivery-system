terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ── Glue Catalog Database ─────────────────────────────────────────────────────
resource "aws_glue_catalog_database" "dijkfood" {
  name        = var.glue_db_name
  description = "Catálogo analítico do dijkfood — gerado pelo Glue Crawler"

  tags = var.common_tags
}

# ── JDBC Connection (RDS Postgres) ────────────────────────────────────────────
resource "aws_glue_connection" "rds" {
  name            = "dijkfood-rds-connection"
  connection_type = "JDBC"

  connection_properties = {
    JDBC_CONNECTION_URL = var.rds_jdbc_url
    USERNAME            = var.rds_username
    PASSWORD            = var.rds_password
  }

  tags = var.common_tags
}

# ── Glue Job: ETL RDS → S3 Parquet ───────────────────────────────────────────
# O script PySpark fica em s3://<scripts_bucket>/glue/etl_rds_to_s3.py
resource "aws_glue_job" "etl_rds_to_s3" {
  name         = "dijkfood-etl-rds-to-s3"
  role_arn     = var.glue_role_arn
  glue_version = "4.0"
  worker_type  = "G.1X"
  number_of_workers = 2

  command {
    name            = "glueetl"
    script_location = "s3://${var.scripts_bucket}/glue/etl_rds_to_s3.py"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-metrics"                   = "true"
    "--enable-auto-scaling"              = "true"
    "--TempDir"                          = "s3://${var.scripts_bucket}/glue/tmp/"

    # passados ao script PySpark
    "--DATA_LAKE_BUCKET"  = var.data_lake_bucket
    "--RDS_JDBC_URL"      = var.rds_jdbc_url
    "--RDS_USERNAME"      = var.rds_username
    "--RDS_PASSWORD"      = var.rds_password
    "--GLUE_DB_NAME"      = var.glue_db_name
    "--GLUE_CONNECTION"   = aws_glue_connection.rds.name
  }

  execution_property {
    max_concurrent_runs = 1
  }

  tags = var.common_tags
}

# ── Glue Crawler: cataloga o S3 Parquet → Glue Catalog ───────────────────────
resource "aws_glue_crawler" "data_lake" {
  name          = "dijkfood-data-lake-crawler"
  role          = var.glue_role_arn
  database_name = aws_glue_catalog_database.dijkfood.name
  description   = "Cataloga os Parquets do data lake para uso no Athena"

  s3_target {
    path = "s3://${var.data_lake_bucket}/analytics/"
  }

  schema_change_policy {
    update_behavior = "UPDATE_IN_DATABASE"
    delete_behavior = "LOG"
  }

  configuration = jsonencode({
    Version = 1.0
    Grouping = {
      TableGroupingPolicy = "CombineCompatibleSchemas"
    }
  })

  tags = var.common_tags
}

# ── Trigger agendado: roda o Job diariamente ──────────────────────────────────
resource "aws_glue_trigger" "daily_etl" {
  name     = "dijkfood-daily-etl"
  type     = "SCHEDULED"
  schedule = var.glue_schedule
  enabled  = true

  actions {
    job_name = aws_glue_job.etl_rds_to_s3.name
  }

  tags = var.common_tags
}

# ── Trigger encadeado: após o Job → roda o Crawler ───────────────────────────
resource "aws_glue_trigger" "crawler_after_etl" {
  name    = "dijkfood-crawler-after-etl"
  type    = "CONDITIONAL"
  enabled = true

  predicate {
    conditions {
      job_name = aws_glue_job.etl_rds_to_s3.name
      state    = "SUCCEEDED"
    }
  }

  actions {
    crawler_name = aws_glue_crawler.data_lake.name
  }

  tags = var.common_tags
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "glue_db_name" {
  value = aws_glue_catalog_database.dijkfood.name
}

output "glue_job_name" {
  value = aws_glue_job.etl_rds_to_s3.name
}

output "glue_crawler_name" {
  value = aws_glue_crawler.data_lake.name
}
