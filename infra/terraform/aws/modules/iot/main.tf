data "aws_caller_identity" "current" {}

resource "aws_sqs_queue" "courier_locations" {
  name                      = "courier-locations"
  message_retention_seconds = 86400
  receive_wait_time_seconds = 0

  tags = var.common_tags
}

resource "aws_iot_topic_rule" "courier_positions" {
  name        = "courier_positions_rule"
  description = "Route courier GPS positions to SQS"
  enabled     = true
  sql         = "SELECT * FROM 'couriers/+/positions'"
  sql_version = "2016-03-23"

  sqs {
    queue_url  = aws_sqs_queue.courier_locations.url
    role_arn   = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/LabRole"
    use_base64 = false
  }
}
