locals {
  is_lambda  = var.runtime == "lambda"
  model_arns = [for id in var.bedrock_model_ids : "arn:aws:bedrock:${var.region}::foundation-model/${id}"]
  tags       = merge(var.tags, { usecase = var.name, health_data = tostring(var.health_data) })
}

# ---------------------------------------------------------------- data at rest
resource "aws_kms_key" "this" {
  description             = "${var.name}: inputs, outputs and queue"
  enable_key_rotation     = true
  deletion_window_in_days = 30
  tags                    = local.tags
}

resource "aws_s3_bucket" "io" {
  bucket_prefix = "${var.name}-io-"
  tags          = local.tags
}

resource "aws_s3_bucket_public_access_block" "io" {
  bucket                  = aws_s3_bucket.io.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "io" {
  bucket = aws_s3_bucket.io.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.this.arn
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "io" {
  bucket = aws_s3_bucket.io.id
  rule {
    id     = "retention"
    status = "Enabled"
    filter {}
    expiration {
      days = var.retention_days
    }
  }
}

# --------------------------------------------------------------------- queue
resource "aws_sqs_queue" "dlq" {
  name                      = "${var.name}-dlq"
  kms_master_key_id         = aws_kms_key.this.arn
  message_retention_seconds = 1209600
  tags                      = local.tags
}

resource "aws_sqs_queue" "work" {
  name                       = "${var.name}-work"
  kms_master_key_id          = aws_kms_key.this.arn
  visibility_timeout_seconds = var.timeout_s * 6
  redrive_policy             = jsonencode({ deadLetterTargetArn = aws_sqs_queue.dlq.arn, maxReceiveCount = 3 })
  tags                       = local.tags
}

# ---------------------------------------------------------------------- role
data "aws_iam_policy_document" "assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = local.is_lambda ? ["lambda.amazonaws.com"] : ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "this" {
  name_prefix        = "${var.name}-"
  assume_role_policy = data.aws_iam_policy_document.assume.json
  tags               = local.tags
}

data "aws_iam_policy_document" "this" {
  statement {
    sid       = "OnlyTheContractsModels"
    actions   = ["bedrock:InvokeModel", "bedrock:Converse"]
    resources = local.model_arns
  }
  statement {
    sid       = "OwnQueue"
    actions   = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:GetQueueAttributes", "sqs:ChangeMessageVisibility"]
    resources = [aws_sqs_queue.work.arn]
  }
  statement {
    sid       = "OwnBucket"
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${aws_s3_bucket.io.arn}/*"]
  }
  statement {
    sid       = "OwnKey"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey"]
    resources = [aws_kms_key.this.arn]
  }
  statement {
    sid       = "QualityMetric"
    actions   = ["cloudwatch:PutMetricData"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "cloudwatch:namespace"
      values   = ["PkvAi"]
    }
  }
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "this" {
  role   = aws_iam_role.this.id
  policy = data.aws_iam_policy_document.this.json
}

# -------------------------------------------------------------------- Lambda
resource "aws_lambda_function" "this" {
  count                          = local.is_lambda ? 1 : 0
  function_name                  = var.name
  package_type                   = "Image"
  image_uri                      = var.image_uri
  role                           = aws_iam_role.this.arn
  memory_size                    = var.memory_mb
  timeout                        = var.timeout_s
  reserved_concurrent_executions = var.concurrency
  kms_key_arn                    = aws_kms_key.this.arn
  environment {
    variables = {
      USECASE        = var.name
      BUCKET         = aws_s3_bucket.io.bucket
      MODEL_IDS      = join(",", var.bedrock_model_ids)
      AWS_REGION_PIN = var.region
    }
  }
  tags = local.tags
}

resource "aws_lambda_event_source_mapping" "this" {
  count            = local.is_lambda ? 1 : 0
  event_source_arn = aws_sqs_queue.work.arn
  function_name    = aws_lambda_function.this[0].arn
  batch_size       = 1
  scaling_config {
    maximum_concurrency = max(2, var.concurrency)
  }
}

# ------------------------------------------------------------------- Fargate
resource "aws_ecs_task_definition" "this" {
  count                    = local.is_lambda ? 0 : 1
  family                   = var.name
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 1024
  memory                   = var.memory_mb
  task_role_arn            = aws_iam_role.this.arn
  execution_role_arn       = aws_iam_role.this.arn
  container_definitions = jsonencode([{
    name      = var.name
    image     = var.image_uri
    essential = true
    environment = [
      { name = "USECASE", value = var.name },
      { name = "QUEUE_URL", value = aws_sqs_queue.work.url },
      { name = "BUCKET", value = aws_s3_bucket.io.bucket },
      { name = "MODEL_IDS", value = join(",", var.bedrock_model_ids) },
    ]
  }])
  tags = local.tags
}

resource "aws_ecs_service" "this" {
  count           = local.is_lambda ? 0 : 1
  name            = var.name
  cluster         = var.ecs_cluster_arn
  task_definition = aws_ecs_task_definition.this[0].arn
  desired_count   = max(2, var.concurrency)
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = var.security_group_ids
    assign_public_ip = false
  }
  tags = local.tags
}

# -------------------------------------------------------------------- alarms
resource "aws_cloudwatch_metric_alarm" "dlq" {
  alarm_name          = "${var.name}-dead-letters"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dlq.name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]
  tags                = local.tags
}

resource "aws_cloudwatch_metric_alarm" "quality" {
  alarm_name          = "${var.name}-reviewed-quality"
  alarm_description   = "Accuracy of the daily sample a person reviews, under the contract's gate."
  namespace           = "PkvAi"
  metric_name         = "ReviewedQuality"
  dimensions          = { UseCase = var.name }
  statistic           = "Average"
  period              = 86400
  evaluation_periods  = 1
  threshold           = var.min_quality
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = var.alarm_topic_arn == "" ? [] : [var.alarm_topic_arn]
  tags                = local.tags
}
