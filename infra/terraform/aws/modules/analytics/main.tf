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
