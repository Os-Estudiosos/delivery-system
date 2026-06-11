resource "aws_sqs_queue" "analytics" {
  name                      = "analytics-events"
  message_retention_seconds = 86400
  receive_wait_time_seconds = 10

  tags = var.common_tags
}

resource "aws_iam_role" "firehose" {
  name = "dijkfood-firehose-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "firehose.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "firehose_s3" {
  name = "dijkfood-firehose-s3-policy"
  role = aws_iam_role.firehose.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:AbortMultipartUpload",
          "s3:GetBucketLocation",
          "s3:GetObject",
          "s3:ListBucket",
          "s3:ListBucketMultipartUploads",
          "s3:PutObject"
        ]
        Resource = [
          var.datalake_bucket_arn,
          "${var.datalake_bucket_arn}/*"
        ]
      }
    ]
  })
}

resource "aws_kinesis_firehose_delivery_stream" "extended_s3_stream" {
  name        = "dijkfood-analytics-stream"
  destination = "extended_s3"

  extended_s3_configuration {
    role_arn   = aws_iam_role.firehose.arn
    bucket_arn = var.datalake_bucket_arn
    prefix     = "events/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/"
    error_output_prefix = "errors/year=!{timestamp:yyyy}/month=!{timestamp:MM}/day=!{timestamp:dd}/!{firehose:error-output-type}/"

    buffering_size     = 5
    buffering_interval = 300
  }

  tags = var.common_tags
}

resource "aws_iam_role" "pipe" {
  name = "dijkfood-pipe-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "pipes.amazonaws.com"
        }
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "pipe_policy" {
  name = "dijkfood-pipe-policy"
  role = aws_iam_role.pipe.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes"
        ]
        Resource = aws_sqs_queue.analytics.arn
      },
      {
        Effect = "Allow"
        Action = [
          "firehose:PutRecord",
          "firehose:PutRecordBatch"
        ]
        Resource = aws_kinesis_firehose_delivery_stream.extended_s3_stream.arn
      }
    ]
  })
}

resource "aws_pipes_pipe" "sqs_to_firehose" {
  name     = "sqs-to-firehose-pipe"
  role_arn = aws_iam_role.pipe.arn
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
