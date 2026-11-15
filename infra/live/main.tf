module "usecase" {
  source   = "../modules/usecase"
  for_each = var.usecases

  name               = each.key
  runtime            = each.value.runtime
  image_uri          = lookup(var.image_uris, each.key, "000000000000.dkr.ecr.${var.region}.amazonaws.com/${each.key}:unset")
  memory_mb          = each.value.memory_mb
  timeout_s          = each.value.timeout_s
  concurrency        = each.value.concurrency
  bedrock_model_ids  = each.value.bedrock_model_ids
  retention_days     = each.value.retention_days
  health_data        = each.value.health_data
  min_quality        = each.value.min_quality
  region             = var.region
  alarm_topic_arn    = var.alarm_topic_arn
  ecs_cluster_arn    = var.ecs_cluster_arn
  subnet_ids         = var.subnet_ids
  security_group_ids = var.security_group_ids
}

output "queues" {
  value = { for k, m in module.usecase : k => m.queue_url }
}
