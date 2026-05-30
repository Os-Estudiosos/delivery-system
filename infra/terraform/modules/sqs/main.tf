terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_sqs_queue" "courier_locations" {
  name                       = "courier-locations"
  visibility_timeout_seconds = 30
  message_retention_seconds  = 300
}