output "ecr_repository_url" {
  value = aws_ecr_repository.app.repository_url
}

output "alb_dns_name" {
  value = aws_lb.api.dns_name
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ses_identity_arn" {
  value = aws_ses_email_identity.sender.arn
}

output "ecs_service_name" {
  value = aws_ecs_service.api.name
}
