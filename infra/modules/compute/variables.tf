variable "environment" {
  description = "Ambiente de despliegue"
  type        = string
  default     = "dev"
}

variable "vpc_id" {
  description = "ID de la VPC"
  type        = string
}

variable "public_subnet_ids" {
  description = "IDs de subredes publicas para ECS/ALB"
  type        = list(string)
}

variable "ecs_security_group_id" {
  description = "Security Group ID para las tareas ECS"
  type        = string
}

variable "alb_security_group_id" {
  description = "Security Group ID para el ALB"
  type        = string
}

variable "database_url" {
  description = "URL de conexión a PostgreSQL"
  type        = string
  sensitive   = true
}

variable "sns_topic_arn" {
  description = "ARN del Topic SNS para publicación de eventos"
  type        = string
}

variable "jwt_secret_key" {
  description = "Clave secreta JWT (minimo 32 caracteres)"
  type        = string
  sensitive   = true
}

variable "app_image" {
  description = "URI de la imagen Docker en ECR"
  type        = string
  default     = "despensa-backend:latest"
}

variable "trusted_proxy_cidr" {
  description = "CIDR confiable para X-Forwarded-For (VPC: el SG de ECS solo admite tráfico del ALB)"
  type        = string
}

variable "notifications_queue_url" {
  description = "URL de la cola SQS de notificaciones que consume el worker"
  type        = string
}

variable "notifications_queue_arn" {
  description = "ARN de la cola SQS de notificaciones (permisos IAM del worker)"
  type        = string
}

variable "ses_from_email" {
  description = "Remitente de los correos. Se crea como identidad SES y hay que verificarla"
  type        = string
}

variable "frontend_base_url" {
  description = "URL pública del frontend, usada en los enlaces de recuperación de contraseña"
  type        = string
}
