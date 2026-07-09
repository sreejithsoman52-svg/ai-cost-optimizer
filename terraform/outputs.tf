output "reports_bucket" {
  value = aws_s3_bucket.reports.bucket
}

output "dynamodb_tables" {
  value = {
    cost     = aws_dynamodb_table.cost_data.name
    waste    = aws_dynamodb_table.waste_data.name
    forecast = aws_dynamodb_table.forecasts.name
    analysis = aws_dynamodb_table.analyses.name
  }
}

output "lambda_function_names" {
  value = {
    cost_collector   = aws_lambda_function.cost_collector.function_name
    waste_detector    = aws_lambda_function.waste_detector.function_name
    bill_forecaster   = aws_lambda_function.bill_forecaster.function_name
    claude_analyser   = aws_lambda_function.claude_analyser.function_name
    report_generator  = aws_lambda_function.report_generator.function_name
    alerter           = aws_lambda_function.alerter.function_name
  }
}

output "anthropic_secret_name" {
  value = aws_secretsmanager_secret.anthropic.name
}

output "ses_sender_identity" {
  value       = aws_ses_email_identity.sender.email
  description = "Remember to click the verification email AWS sends to this address"
}
