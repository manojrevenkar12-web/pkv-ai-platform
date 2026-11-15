output "queue_url" {
  value = aws_sqs_queue.work.url
}

output "bucket" {
  value = aws_s3_bucket.io.bucket
}

output "role_arn" {
  value = aws_iam_role.this.arn
}
