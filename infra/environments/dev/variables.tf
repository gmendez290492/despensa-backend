variable "aws_region" {
  description = "Region de AWS"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Ambiente"
  type        = string
  default     = "dev"
}

variable "db_password" {
  description = "Contraseña de la base de datos PostgreSQL en RDS"
  type        = string
  sensitive   = true
}

variable "jwt_secret_key" {
  description = "Clave secreta para firma de tokens JWT"
  type        = string
  sensitive   = true
}

variable "budget_notification_email" {
  description = "Email para recibir alertas de costos si supera $5 USD"
  type        = string
  default     = "alertas@despensa.local"
}
