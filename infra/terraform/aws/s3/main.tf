terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_s3_bucket" "dijkfood" {
  bucket        = "dijkfood-assets"
  force_destroy = false
}

resource "aws_s3_bucket_ownership_controls" "dijkfood" {
  bucket = aws_s3_bucket.dijkfood.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}

resource "aws_s3_bucket_versioning" "dijkfood" {
  bucket = aws_s3_bucket.dijkfood.id
  versioning_configuration {
    status = "Enabled"
  }
}
