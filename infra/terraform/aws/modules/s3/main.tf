resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "assets" {
  bucket        = "dijkfood-assets-${random_id.bucket_suffix.hex}"
  force_destroy = true

  tags = var.common_tags
}

resource "aws_s3_bucket_ownership_controls" "assets" {
  bucket = aws_s3_bucket.assets.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_versioning" "assets" {
  bucket = aws_s3_bucket.assets.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket" "datalake" {
  bucket        = "dijkfood-datalake-${random_id.bucket_suffix.hex}"
  force_destroy = true

  tags = var.common_tags
}

resource "aws_s3_bucket_ownership_controls" "datalake" {
  bucket = aws_s3_bucket.datalake.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_versioning" "datalake" {
  bucket = aws_s3_bucket.datalake.id
  versioning_configuration {
    status = "Enabled"
  }
}

output "assets_bucket_name" {
  value = aws_s3_bucket.assets.id
}

output "datalake_bucket_name" {
  value = aws_s3_bucket.datalake.id
}

output "datalake_bucket_arn" {
  value = aws_s3_bucket.datalake.arn
}
