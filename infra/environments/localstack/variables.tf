variable "aws_region" {
  description = "Region simulada"
  type        = string
  default     = "us-east-1"
}

variable "localstack_endpoint" {
  description = "Endpoint de LocalStack o AWS Emulator"
  type        = string
  default     = "http://localhost:9297"
}

variable "db_password" {
  description = "Password de base de datos"
  type        = string
  default     = "localstack_secret_pwd"
}

variable "jwt_secret_key" {
  description = "Clave secreta JWT"
  type        = string
  default     = "localstack-test-secret-key-at-least-32chars"
}
