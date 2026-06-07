terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# ── Bucket principal do data lake ─────────────────────────────────────────────
resource "aws_s3_bucket" "data_lake" {
  bucket        = var.data_lake_bucket
  force_destroy = false

  tags = var.common_tags
}

resource "aws_s3_bucket_ownership_controls" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

# ── Prefixos lógicos (objetos placeholder para estrutura) ─────────────────────
# analytics/orders/year=YYYY/month=MM/day=DD/
# analytics/events/...
# glue-scripts/

resource "aws_s3_object" "prefix_analytics" {
  bucket  = aws_s3_bucket.data_lake.id
  key     = "analytics/.keep"
  content = ""

  tags = var.common_tags
}

resource "aws_s3_object" "prefix_scripts" {
  bucket  = aws_s3_bucket.data_lake.id
  key     = "glue-scripts/.keep"
  content = ""

  tags = var.common_tags
}

# ── Lifecycle: compacta versões antigas depois de 90 dias ─────────────────────
resource "aws_s3_bucket_lifecycle_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id

  rule {
    id     = "archive-old-parquet"
    status = "Enabled"

    filter { prefix = "analytics/" }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }

    transition {
      days          = 365
      storage_class = "GLACIER"
    }
  }
}

# ── Outputs ───────────────────────────────────────────────────────────────────
output "data_lake_bucket" {
  value = aws_s3_bucket.data_lake.bucket
}

output "scripts_prefix" {
  value = "s3://${aws_s3_bucket.data_lake.bucket}/glue-scripts/"
}
