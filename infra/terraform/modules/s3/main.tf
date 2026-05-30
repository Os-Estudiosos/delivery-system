terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

variable "is_local" { default = true }

resource "aws_s3_bucket" "dijkfood" {
  bucket = "dijkfood-assets"

  # LocalStack não suporta force_destroy em alguns casos
  force_destroy = var.is_local
}

resource "aws_s3_bucket_ownership_controls" "dijkfood" {
  bucket = aws_s3_bucket.dijkfood.id
  rule {
    object_ownership = "BucketOwnerPreferred"
  }
}