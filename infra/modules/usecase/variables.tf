variable "name" {
  description = "Use-case name from its contract, e.g. invoice-check."
  type        = string
}

variable "runtime" {
  description = "lambda or fargate, decided by the feasibility check."
  type        = string
  validation {
    condition     = contains(["lambda", "fargate"], var.runtime)
    error_message = "runtime must be lambda or fargate."
  }
}

variable "image_uri" {
  description = "Container image of the use case; the same image runs on Lambda and on Fargate."
  type        = string
}

variable "memory_mb" {
  type = number
}

variable "timeout_s" {
  type = number
}

variable "concurrency" {
  description = "Reserved concurrency (Lambda) or task count (Fargate) at the contract's peak."
  type        = number
}

variable "bedrock_model_ids" {
  description = "The only foundation models this use case may call."
  type        = list(string)
}

variable "retention_days" {
  type = number
}

variable "health_data" {
  type = bool
}

variable "min_quality" {
  description = "The contract's gate: the reviewed-sample metric alarms below it."
  type        = number
}

variable "region" {
  type = string
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

variable "alarm_topic_arn" {
  type    = string
  default = ""
}

variable "tags" {
  type    = map(string)
  default = {}
}
