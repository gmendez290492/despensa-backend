# 1. Repositorio ECR con escaneo de vulnerabilidades
resource "aws_ecr_repository" "app" {
  name                 = "despensa-backend-${var.environment}"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Name        = "despensa-ecr-${var.environment}"
    Environment = var.environment
  }
}

# 2. Cluster ECS Fargate
resource "aws_ecs_cluster" "main" {
  name = "despensa-cluster-${var.environment}"

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = {
    Name        = "despensa-ecs-cluster-${var.environment}"
    Environment = var.environment
  }
}

# 3. Log Group en CloudWatch
resource "aws_cloudwatch_log_group" "ecs" {
  name              = "/ecs/despensa-${var.environment}"
  retention_in_days = 7

  tags = {
    Name        = "despensa-logs-${var.environment}"
    Environment = var.environment
  }
}

# 4. Roles IAM
resource "aws_iam_role" "ecs_execution_role" {
  name = "despensa-ecs-execution-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action    = "sts:AssumeRole"
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "ecs_execution" {
  role       = aws_iam_role.ecs_execution_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

resource "aws_iam_role" "ecs_task_role" {
  name = "despensa-ecs-task-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action    = "sts:AssumeRole"
        Effect    = "Allow"
        Principal = { Service = "ecs-tasks.amazonaws.com" }
      }
    ]
  })
}

# Política de mínimo privilegio para que la tarea publique en SNS
resource "aws_iam_role_policy" "ecs_task_sns" {
  name = "despensa-task-sns-policy-${var.environment}"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = var.sns_topic_arn
      }
    ]
  })
}

# Identidad SES del remitente. AWS envía un correo de verificación a esa dirección.
# Mientras la cuenta esté en el sandbox de SES, los destinatarios también deben verificarse.
resource "aws_ses_email_identity" "sender" {
  email = var.ses_from_email
}

# El worker (sidecar de la tarea) consume la cola de notificaciones y envía con SES
resource "aws_iam_role_policy" "ecs_task_worker" {
  name = "despensa-task-worker-policy-${var.environment}"
  role = aws_iam_role.ecs_task_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "sqs:ReceiveMessage",
          "sqs:DeleteMessage",
          "sqs:ChangeMessageVisibility",
          "sqs:GetQueueAttributes"
        ]
        Resource = var.notifications_queue_arn
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = aws_ses_email_identity.sender.arn
      }
    ]
  })
}

# 5. Application Load Balancer
resource "aws_lb" "api" {
  name               = "despensa-alb-${var.environment}"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [var.alb_security_group_id]
  subnets            = var.public_subnet_ids

  tags = {
    Name        = "despensa-alb-${var.environment}"
    Environment = var.environment
  }
}

resource "aws_lb_target_group" "api" {
  name        = "despensa-tg-${var.environment}"
  port        = 8000
  protocol    = "HTTP"
  vpc_id      = var.vpc_id
  target_type = "ip"

  health_check {
    path                = "/health/live"
    healthy_threshold   = 2
    unhealthy_threshold = 3
    timeout             = 5
    interval            = 15
    matcher             = "200"
  }
}

resource "aws_lb_listener" "http" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

# 6. Definición de Tarea ECS Fargate: API + worker como sidecar.
# Comparten CPU/memoria de la tarea para no pagar una segunda tarea Fargate.
locals {
  common_environment = [
    { name = "ENVIRONMENT", value = var.environment },
    { name = "DATABASE_URL", value = var.database_url },
    { name = "JWT_SECRET_KEY", value = var.jwt_secret_key },
    { name = "AWS_DEFAULT_REGION", value = "us-east-1" },
    { name = "SNS_TOPIC_ARN", value = var.sns_topic_arn },
    { name = "FRONTEND_BASE_URL", value = var.frontend_base_url }
  ]
}

resource "aws_ecs_task_definition" "api" {
  family                   = "despensa-api-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.ecs_execution_role.arn
  task_role_arn            = aws_iam_role.ecs_task_role.arn

  container_definitions = jsonencode([
    {
      name      = "api"
      image     = var.app_image
      essential = true
      portMappings = [
        {
          containerPort = 8000
          hostPort      = 8000
        }
      ]
      environment = concat(local.common_environment, [
        { name = "RATE_LIMIT_BACKEND", value = "postgres" },
        { name = "FORWARDED_ALLOW_IPS", value = var.trusted_proxy_cidr }
      ])
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = "us-east-1"
          "awslogs-stream-prefix" = "api"
        }
      }
    },
    {
      name    = "worker"
      image   = var.app_image
      command = ["python", "-m", "app.worker"]
      # No esencial: si el worker cae, la API sigue sirviendo. ECS lo reinicia en el
      # sitio y los eventos esperan en el Outbox y en SQS (con DLQ) mientras tanto.
      essential = false
      restartPolicy = {
        enabled              = true
        restartAttemptPeriod = 60
      }
      environment = concat(local.common_environment, [
        { name = "APP_NAME", value = "Despensa Worker" },
        { name = "MESSAGING_BACKEND", value = "aws" },
        { name = "EMAIL_BACKEND", value = "ses" },
        { name = "SQS_NOTIFICATIONS_QUEUE_URL", value = var.notifications_queue_url },
        { name = "SMTP_FROM_EMAIL", value = var.ses_from_email }
      ])
      logConfiguration = {
        logDriver = "awslogs"
        options = {
          "awslogs-group"         = aws_cloudwatch_log_group.ecs.name
          "awslogs-region"        = "us-east-1"
          "awslogs-stream-prefix" = "worker"
        }
      }
    }
  ])
}

# 7. Servicio ECS
resource "aws_ecs_service" "api" {
  name            = "despensa-api-service-${var.environment}"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = var.public_subnet_ids
    security_groups  = [var.ecs_security_group_id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  depends_on = [aws_lb_listener.http]
}
