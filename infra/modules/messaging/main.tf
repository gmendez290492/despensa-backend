# 1. SNS Topic principal para el bus de eventos
resource "aws_sns_topic" "events" {
  name = "despensa-events-${var.environment}"

  tags = {
    Name        = "despensa-events-${var.environment}"
    Environment = var.environment
  }
}

# 2. Dead Letter Queues (DLQs)
resource "aws_sqs_queue" "notifications_dlq" {
  name                      = "despensa-notifications-dlq-${var.environment}"
  message_retention_seconds = 1209600 # 14 dias

  tags = {
    Name        = "despensa-notifications-dlq-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_sqs_queue" "recipes_dlq" {
  name                      = "despensa-recipes-dlq-${var.environment}"
  message_retention_seconds = 1209600

  tags = {
    Name        = "despensa-recipes-dlq-${var.environment}"
    Environment = var.environment
  }
}

# 3. Colas SQS principales con Redrive Policy hacia las DLQs
resource "aws_sqs_queue" "notifications_queue" {
  name                       = "despensa-notifications-queue-${var.environment}"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600 # 4 dias

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.notifications_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "despensa-notifications-queue-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_sqs_queue" "recipes_queue" {
  name                       = "despensa-recipes-queue-${var.environment}"
  visibility_timeout_seconds = 60
  message_retention_seconds  = 345600

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.recipes_dlq.arn
    maxReceiveCount     = 3
  })

  tags = {
    Name        = "despensa-recipes-queue-${var.environment}"
    Environment = var.environment
  }
}

# 4. Políticas de SQS para permitir publicación desde SNS
resource "aws_sqs_queue_policy" "notifications_policy" {
  queue_url = aws_sqs_queue.notifications_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowSNSMessages"
        Effect    = "Allow"
        Principal = { Service = "sns.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.notifications_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.events.arn
          }
        }
      }
    ]
  })
}

resource "aws_sqs_queue_policy" "recipes_policy" {
  queue_url = aws_sqs_queue.recipes_queue.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid       = "AllowSNSMessages"
        Effect    = "Allow"
        Principal = { Service = "sns.amazonaws.com" }
        Action    = "sqs:SendMessage"
        Resource  = aws_sqs_queue.recipes_queue.arn
        Condition = {
          ArnEquals = {
            "aws:SourceArn" = aws_sns_topic.events.arn
          }
        }
      }
    ]
  })
}

# 5. Suscripciones SNS -> SQS con Filter Policies
resource "aws_sns_topic_subscription" "notifications_subscription" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.notifications_queue.arn

  filter_policy = jsonencode({
    event_type = [
      "user.registered.v1",
      "pantry.item_expiring_soon.v1",
      "notification.expiration_alert.v1"
    ]
  })
}

resource "aws_sns_topic_subscription" "recipes_subscription" {
  topic_arn = aws_sns_topic.events.arn
  protocol  = "sqs"
  endpoint  = aws_sqs_queue.recipes_queue.arn

  filter_policy = jsonencode({
    event_type = [
      "pantry.item_added.v1",
      "pantry.item_consumed.v1"
    ]
  })
}
