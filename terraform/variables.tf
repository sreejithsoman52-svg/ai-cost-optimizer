variable "aws_region" {
  default = "eu-central-1"
}

variable "reports_bucket_name" {
  description = "Unique S3 bucket name for reports (must be globally unique)"
}

variable "anthropic_api_key" {
  description = "Anthropic API key, stored in Secrets Manager"
  sensitive   = true
}

variable "sender_email" {
  description = "Verified SES sender email"
}

variable "recipient_email" {
  description = "Email address to receive cost alerts"
}

variable "monthly_budget_usd" {
  description = "Monthly AWS budget threshold that triggers an alert if forecast exceeds it"
  default     = "1000"
}

variable "slack_webhook_url" {
  description = "Optional Slack incoming webhook URL for alerts"
  default     = ""
}
