resource "aws_sqs_queue" "courier_locations" {
  name                      = "courier-locations"
  message_retention_seconds = 86400
  receive_wait_time_seconds = 0

  tags = var.common_tags
}

resource "aws_iam_role" "iot_sqs" {
  name = "dijkfood-iot-sqs-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "iot.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })

  tags = var.common_tags
}

resource "aws_iam_role_policy" "iot_sqs" {
  name = "dijkfood-iot-sqs-policy"
  role = aws_iam_role.iot_sqs.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage"
        ]
        Resource = aws_sqs_queue.courier_locations.arn
      }
    ]
  })
}

resource "aws_iot_topic_rule" "courier_positions" {
  name        = "courier_positions_rule"
  description = "Route courier GPS positions to SQS"
  enabled     = true
  sql         = "SELECT * FROM 'couriers/+/positions'"
  sql_version = "2016-03-23"

  sqs {
    queue_url  = aws_sqs_queue.courier_locations.url
    role_arn   = aws_iam_role.iot_sqs.arn
    use_base64 = false
  }
}
