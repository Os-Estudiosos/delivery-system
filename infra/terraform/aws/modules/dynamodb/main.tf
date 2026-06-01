terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_dynamodb_table" "courier_positions" {
  name         = "courier_positions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "courier_id"
  range_key    = "timestamp"

  attribute {
    name = "courier_id"
    type = "N"
  }

  attribute {
    name = "timestamp"
    type = "S"
  }

  attribute {
    name = "delivery_id"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi-delivery"
    hash_key        = "delivery_id"
    range_key       = "timestamp"
    projection_type = "ALL"
    write_capacity  = 0
    read_capacity   = 0
  }
}
