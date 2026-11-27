resource "aws_db_subnet_group" "main" {
  name       = "despensa-db-subnet-group-${var.environment}"
  subnet_ids = var.private_subnet_ids

  tags = {
    Name        = "despensa-db-subnet-group-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_db_instance" "postgres" {
  identifier            = "despensa-pg-${var.environment}"
  engine                = "postgres"
  engine_version        = "16.3"
  instance_class        = var.instance_class
  allocated_storage     = 20
  max_allocated_storage = 50
  storage_type          = "gp3"
  storage_encrypted     = true

  db_name  = var.db_name
  username = var.db_username
  password = var.db_password

  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [var.database_security_group_id]

  publicly_accessible = false
  skip_final_snapshot = true # Permite terraform destroy en dev sin cargos extra

  backup_retention_period = 7
  deletion_protection     = false

  tags = {
    Name        = "despensa-postgres-${var.environment}"
    Environment = var.environment
  }
}
