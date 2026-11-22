variable "environment" {
  description = "Ambiente de despliegue"
  type        = string
  default     = "dev"
}

variable "private_subnet_ids" {
  description = "IDs de subredes privadas para el DB subnet group"
  type        = list(string)
}

variable "database_security_group_id" {
  description = "Security Group ID para RDS"
  type        = string
}

variable "db_name" {
  description = "Nombre de la base de datos PostgreSQL"
  type        = string
  default     = "despensa"
}

variable "db_username" {
  description = "Usuario administrador de PostgreSQL"
  type        = string
  default     = "despensa_admin"
}

variable "db_password" {
  description = "Contraseña maestra de PostgreSQL"
  type        = string
  sensitive   = true
}

variable "instance_class" {
  description = "Tipo de instancia RDS para desarrollo a mínimo costo"
  type        = string
  default     = "db.t4g.micro"
}
