variable "region" {
  type    = string
  default = "eu-central-1"
}

variable "usecases" {
  description = "Written by scripts/design.py from the contracts and the feasibility check. Do not edit by hand."
  type = map(object({
    runtime           = string
    memory_mb         = number
    timeout_s         = number
    concurrency       = number
    bedrock_model_ids = list(string)
    retention_days    = number
    health_data       = bool
    min_quality       = number
  }))
}

variable "image_uris" {
  description = "Container image per use case, set by the release pipeline."
  type        = map(string)
  default     = {}
}

variable "alarm_topic_arn" {
  type    = string
  default = ""
}

variable "ecs_cluster_arn" {
  type    = string
  default = ""
}

variable "subnet_ids" {
  type    = list(string)
  default = []
}

variable "security_group_ids" {
  type    = list(string)
  default = []
}
