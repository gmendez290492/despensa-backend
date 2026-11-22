output "sns_topic_arn" {
  value = aws_sns_topic.events.arn
}

output "notifications_queue_arn" {
  value = aws_sqs_queue.notifications_queue.arn
}

output "notifications_queue_url" {
  value = aws_sqs_queue.notifications_queue.id
}

output "recipes_queue_arn" {
  value = aws_sqs_queue.recipes_queue.arn
}

output "recipes_queue_url" {
  value = aws_sqs_queue.recipes_queue.id
}
