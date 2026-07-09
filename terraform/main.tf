provider "aws" { region = var.aws_region }

# ── DynamoDB Tables ─────────────────────────────────────────
resource "aws_dynamodb_table" "cost_data" {
  name         = "ai-cost-optimizer-costs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute { name = "pk", type = "S" }
  attribute { name = "sk", type = "S" }
  ttl { attribute_name = "ttl", enabled = true }
  tags = { Project = "AI-Cost-Optimizer" }
}

resource "aws_dynamodb_table" "waste_data" {
  name         = "ai-cost-optimizer-waste"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute { name = "pk", type = "S" }
  attribute { name = "sk", type = "S" }
  tags = { Project = "AI-Cost-Optimizer" }
}

resource "aws_dynamodb_table" "forecasts" {
  name         = "ai-cost-optimizer-forecasts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute { name = "pk", type = "S" }
  attribute { name = "sk", type = "S" }
  tags = { Project = "AI-Cost-Optimizer" }
}

resource "aws_dynamodb_table" "analyses" {
  name         = "ai-cost-optimizer-analyses"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute { name = "pk", type = "S" }
  attribute { name = "sk", type = "S" }
  tags = { Project = "AI-Cost-Optimizer" }
}

# ── S3 Bucket for Reports ────────────────────────────────────
resource "aws_s3_bucket" "reports" {
  bucket = var.reports_bucket_name
  tags   = { Project = "AI-Cost-Optimizer" }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "reports" {
  bucket = aws_s3_bucket.reports.id
  rule { apply_server_side_encryption_by_default { sse_algorithm = "AES256" } }
}

# ── SES sender identity ───────────────────────────────────────
# NOTE: after `terraform apply`, AWS emails a verification link to
# var.sender_email — you must click it before SendEmail will work.
resource "aws_ses_email_identity" "sender" {
  email = var.sender_email
}

# ── Secrets Manager (Anthropic API Key) ──────────────────────
resource "aws_secretsmanager_secret" "anthropic" {
  name = "anthropic-api-key-cost-optimizer"
}
resource "aws_secretsmanager_secret_version" "anthropic" {
  secret_id     = aws_secretsmanager_secret.anthropic.id
  secret_string = jsonencode({ api_key = var.anthropic_api_key })
}

# ── IAM Role for all Lambdas ─────────────────────────────────
resource "aws_iam_role" "lambda_role" {
  name = "ai-cost-optimizer-lambda-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "ai-cost-optimizer-policy"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ce:GetCostAndUsage", "ce:GetCostForecast", "support:*"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["ec2:Describe*", "cloudwatch:GetMetricStatistics",
        "elasticloadbalancing:DescribeLoadBalancers"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = ["dynamodb:PutItem", "dynamodb:GetItem", "dynamodb:Scan", "dynamodb:Query"]
        Resource = [
          aws_dynamodb_table.cost_data.arn,
          aws_dynamodb_table.waste_data.arn,
          aws_dynamodb_table.forecasts.arn,
          aws_dynamodb_table.analyses.arn,
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject", "s3:GetObject"]
        Resource = "${aws_s3_bucket.reports.arn}/*"
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.anthropic.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ses:SendEmail", "ses:SendRawEmail"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })
}

# ── Lambda: Cost Collector ───────────────────────────────────
resource "aws_lambda_function" "cost_collector" {
  filename         = "../lambdas/cost_collector.zip"
  source_code_hash = filebase64sha256("../lambdas/cost_collector.zip")
  function_name    = "ai-cost-collector"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 120
  memory_size      = 256
  environment {
    variables = { COST_TABLE = aws_dynamodb_table.cost_data.name }
  }
}

# ── Lambda: Waste Detector ───────────────────────────────────
resource "aws_lambda_function" "waste_detector" {
  filename         = "../lambdas/waste_detector.zip"
  source_code_hash = filebase64sha256("../lambdas/waste_detector.zip")
  function_name    = "ai-waste-detector"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 180
  memory_size      = 256
  environment {
    variables = { WASTE_TABLE = aws_dynamodb_table.waste_data.name }
  }
}

# ── Lambda: Bill Forecaster ──────────────────────────────────
resource "aws_lambda_function" "bill_forecaster" {
  filename         = "../lambdas/bill_forecaster.zip"
  source_code_hash = filebase64sha256("../lambdas/bill_forecaster.zip")
  function_name    = "ai-bill-forecaster"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  environment {
    variables = {
      COST_TABLE     = aws_dynamodb_table.cost_data.name
      FORECAST_TABLE = aws_dynamodb_table.forecasts.name
    }
  }
}

# ── Lambda: Claude AI Analyser ───────────────────────────────
resource "aws_lambda_function" "claude_analyser" {
  filename         = "../lambdas/claude_analyser.zip"
  source_code_hash = filebase64sha256("../lambdas/claude_analyser.zip")
  function_name    = "ai-claude-analyser"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 90
  memory_size      = 256
  environment {
    variables = {
      WASTE_TABLE    = aws_dynamodb_table.waste_data.name
      FORECAST_TABLE = aws_dynamodb_table.forecasts.name
      ANALYSIS_TABLE = aws_dynamodb_table.analyses.name
      SECRET_NAME    = aws_secretsmanager_secret.anthropic.name
    }
  }
}

# ── Lambda: Report Generator ─────────────────────────────────
resource "aws_lambda_function" "report_generator" {
  filename         = "../lambdas/report_generator.zip"
  source_code_hash = filebase64sha256("../lambdas/report_generator.zip")
  function_name    = "ai-report-generator"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  environment {
    variables = {
      ANALYSIS_TABLE = aws_dynamodb_table.analyses.name
      WASTE_TABLE    = aws_dynamodb_table.waste_data.name
      REPORT_BUCKET  = aws_s3_bucket.reports.bucket
    }
  }
}

# ── Lambda: Alerter ──────────────────────────────────────────
resource "aws_lambda_function" "alerter" {
  filename         = "../lambdas/alerter.zip"
  source_code_hash = filebase64sha256("../lambdas/alerter.zip")
  function_name    = "ai-cost-alerter"
  role             = aws_iam_role.lambda_role.arn
  handler          = "handler.lambda_handler"
  runtime          = "python3.12"
  timeout          = 60
  memory_size      = 256
  environment {
    variables = {
      ANALYSIS_TABLE    = aws_dynamodb_table.analyses.name
      FORECAST_TABLE    = aws_dynamodb_table.forecasts.name
      SENDER_EMAIL      = var.sender_email
      RECIPIENT_EMAIL   = var.recipient_email
      SLACK_WEBHOOK_URL = var.slack_webhook_url
      MONTHLY_BUDGET_USD = var.monthly_budget_usd
    }
  }
}

# ── EventBridge: daily pipeline, staggered 5 min apart ───────
# Each stage depends on the previous stage's DynamoDB writes,
# so they are scheduled sequentially rather than all at once.
locals {
  schedule = {
    cost_collector   = "cron(0 8 * * ? *)"
    waste_detector   = "cron(5 8 * * ? *)"
    bill_forecaster  = "cron(10 8 * * ? *)"
    claude_analyser  = "cron(15 8 * * ? *)"
    alerter          = "cron(25 8 * * ? *)"
  }
  functions = {
    cost_collector   = aws_lambda_function.cost_collector
    waste_detector   = aws_lambda_function.waste_detector
    bill_forecaster  = aws_lambda_function.bill_forecaster
    claude_analyser  = aws_lambda_function.claude_analyser
    alerter          = aws_lambda_function.alerter
  }
}

resource "aws_cloudwatch_event_rule" "daily" {
  for_each            = local.schedule
  name                = "ai-cost-optimizer-${each.key}"
  schedule_expression = each.value
}

resource "aws_cloudwatch_event_target" "daily" {
  for_each  = local.schedule
  rule      = aws_cloudwatch_event_rule.daily[each.key].name
  target_id = each.key
  arn       = local.functions[each.key].arn
}

resource "aws_lambda_permission" "allow_eventbridge_daily" {
  for_each      = local.schedule
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = local.functions[each.key].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily[each.key].arn
}

# ── EventBridge: Weekly report on Mondays at 08:30 ───────────
resource "aws_cloudwatch_event_rule" "weekly_report" {
  name                = "ai-cost-optimizer-weekly"
  schedule_expression = "cron(30 8 ? * MON *)"
}

resource "aws_cloudwatch_event_target" "start_report" {
  rule      = aws_cloudwatch_event_rule.weekly_report.name
  target_id = "ReportGenerator"
  arn       = aws_lambda_function.report_generator.arn
}

resource "aws_lambda_permission" "allow_eventbridge_weekly" {
  statement_id  = "AllowEventBridgeInvokeWeekly"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.report_generator.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.weekly_report.arn
}
