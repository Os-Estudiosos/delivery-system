data "aws_caller_identity" "current" {}

resource "aws_sqs_queue" "analytics" {
  name                      = "analytics-events"
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10

  tags = var.common_tags
}

resource "aws_kinesis_firehose_delivery_stream" "extended_s3_stream" {
  name        = "dijkfood-analytics-stream"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn   = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/LabRole"
    bucket_arn = var.datalake_bucket_arn
    prefix     = "events/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/"
    error_output_prefix = "errors/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/!{firehose:error-output-type}/"

    buffering_size     = 5
    buffering_interval = 300
  }

  tags = var.common_tags
}

resource "aws_pipes_pipe" "sqs_to_firehose" {
  name     = "sqs-to-firehose-pipe"
  role_arn = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/LabRole"
  source   = aws_sqs_queue.analytics.arn
  target   = aws_kinesis_firehose_delivery_stream.extended_s3_stream.arn

  source_parameters {
    sqs_queue_parameters {
      batch_size = 10
    }
  }

  target_parameters {
    input_template = "{\"order_id\": <$.body.order_id>, \"status\": \"<$.body.status>\", \"restaurant_id\": <$.body.restaurant_id>, \"region_id\": <$.body.region_id>, \"timestamp\": \"<$.body.timestamp>\"}\n"
  }

  tags = var.common_tags
}

resource "aws_glue_catalog_database" "dijkfood" {
  name = "dijkfood_analytics"
}

resource "aws_athena_workgroup" "dijkfood" {
  name = "dijkfood"

  configuration {
    enforce_workgroup_configuration    = true
    publish_cloudwatch_metrics_enabled = true

    result_configuration {
      output_location = "s3://${var.datalake_bucket_name}/athena-results/"
    }
  }

  tags = var.common_tags
}

resource "aws_glue_catalog_table" "events" {
  name          = "events"
  database_name = aws_glue_catalog_database.dijkfood.name

  table_type = "EXTERNAL_TABLE"

  parameters = {
    "classification"         = "json"
    "projection.enabled"     = "true"
    "projection.year.type"   = "integer"
    "projection.year.range"  = "2023,2030"
    "projection.year.digits" = "4"
    "projection.month.type"  = "integer"
    "projection.month.range" = "01,12"
    "projection.month.digits"= "2"
    "projection.day.type"    = "integer"
    "projection.day.range"   = "01,31"
    "projection.day.digits"  = "2"
    "storage.location.template" = "s3://${var.datalake_bucket_name}/events/year=$${year}/month=$${month}/day=$${day}/"
  }

  storage_descriptor {
    location      = "s3://${var.datalake_bucket_name}/events/"
    input_format  = "org.apache.hadoop.mapred.TextInputFormat"
    output_format = "org.apache.hadoop.hive.ql.io.IgnoreKeyTextOutputFormat"

    ser_de_info {
      name                  = "json"
      serialization_library = "org.openx.data.jsonserde.JsonSerDe"
      parameters = {
        "ignore.malformed.json" = "true"
      }
    }

    columns {
      name = "order_id"
      type = "int"
    }
    columns {
      name = "status"
      type = "string"
    }
    columns {
      name = "restaurant_id"
      type = "int"
    }
    columns {
      name = "region_id"
      type = "int"
    }
    columns {
      name = "timestamp"
      type = "string"
    }
  }

  partition_keys {
    name = "year"
    type = "string"
  }
  partition_keys {
    name = "month"
    type = "string"
  }
  partition_keys {
    name = "day"
    type = "string"
  }
}
