terraform {
  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }

  # Configurable para guardar el estado en S3 con DynamoDB locking
  # backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Despensa"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# 1. Modulo de Red
module "network" {
  source      = "../../modules/network"
  environment = var.environment
}

# 2. Modulo de Base de Datos
module "database" {
  source                     = "../../modules/database"
  environment                = var.environment
  private_subnet_ids         = module.network.private_subnet_ids
  database_security_group_id = module.network.database_security_group_id
  db_password                = var.db_password
}

# 3. Modulo de Mensajeria (SNS + SQS + DLQ)
module "messaging" {
  source      = "../../modules/messaging"
  environment = var.environment
}

# 4. Modulo de Computo (ECS + ALB + ECR)
module "compute" {
  source                = "../../modules/compute"
  environment           = var.environment
  vpc_id                = module.network.vpc_id
  public_subnet_ids     = module.network.public_subnet_ids
  ecs_security_group_id = module.network.ecs_security_group_id
  alb_security_group_id = module.network.alb_security_group_id
  database_url          = module.database.database_url
  sns_topic_arn         = module.messaging.sns_topic_arn
  jwt_secret_key        = var.jwt_secret_key
  trusted_proxy_cidr    = module.network.vpc_cidr
  frontend_base_url     = var.frontend_base_url
}

# 5. Control de Costos: Alerta de AWS Budgets a $5 USD
resource "aws_budgets_budget" "cost_limit" {
  name         = "despensa-budget-${var.environment}"
  budget_type  = "COST"
  limit_amount = "5.0"
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 80
    threshold_type             = "PERCENTAGE"
    notification_type          = "ACTUAL"
    subscriber_email_addresses = [var.budget_notification_email]
  }

  notification {
    comparison_operator        = "GREATER_THAN"
    threshold                  = 100
    threshold_type             = "PERCENTAGE"
    notification_type          = "FORECASTED"
    subscriber_email_addresses = [var.budget_notification_email]
  }
}
