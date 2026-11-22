terraform {
  required_version = ">= 1.8.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.50"
    }
  }
}

provider "aws" {
  region                      = var.aws_region
  access_key                  = "mock_key"
  secret_key                  = "mock_secret"
  skip_credentials_validation = true
  skip_metadata_api_check     = true
  skip_requesting_account_id  = true

  endpoints {
    sns = var.localstack_endpoint
    sqs = var.localstack_endpoint
    s3  = var.localstack_endpoint
    ecr = var.localstack_endpoint
  }
}

# Modulo de Mensajeria (SNS + SQS) probado localmente a $0 USD
module "messaging" {
  source      = "../../modules/messaging"
  environment = "localstack"
}

output "sns_topic_arn" {
  value = module.messaging.sns_topic_arn
}

output "notifications_queue_url" {
  value = module.messaging.notifications_queue_url
}
