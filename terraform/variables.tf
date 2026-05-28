variable "aws_region"           { default = "eu-central-1" }
variable "reports_bucket_name"  { description = "Unique S3 bucket name for reports" }
variable "anthropic_api_key"    { sensitive = true }
variable "sender_email"         { description = "Verified SES sender email" }
variable "recipient_email"      { description = "Email to receive alerts" }
variable "monthly_budget_usd"   { default = "1000" }
variable "slack_webhook_url"    { default = "" }
