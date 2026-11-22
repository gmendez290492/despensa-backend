output "api_url" {
  description = "URL publica del Application Load Balancer para acceder a la API"
  value       = "http://${module.compute.alb_dns_name}"
}

output "ecr_repository_url" {
  value = module.compute.ecr_repository_url
}

output "sns_topic_arn" {
  value = module.messaging.sns_topic_arn
}

output "database_endpoint" {
  value = module.database.endpoint
}
