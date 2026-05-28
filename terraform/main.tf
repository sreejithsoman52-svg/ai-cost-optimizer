provider "aws" { region = var.aws_region }

# ── DynamoDB Tables ─────────────────────────────────────────
resource "aws_dynamodb_table" "cost_data" {
  name         = "ai-cost-optimizer-costs"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute { name = "pk" type = "S" }
  attribute { name = "sk" type = "S" }
  ttl { attribute_name = "ttl" enabled = true }
  tags = { Project = "AI-Cost-Optimizer" }
}

resource "aws_dynamodb_table" "waste_data" {
  name         = "ai-cost-optimizer-waste"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute { name = "pk" type = "S" }
  attribute { name = "sk" type = "S" }
}

resource "aws_dynamodb_table" "forecasts" {
  name         = "ai-cost-optimizer-forecasts"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute { name = "pk" type = "S" }
  attribute { name = "sk" type = "S" }
}

resource "aws_dynamodb_table" "analyses" {
  name         = "ai-cost-optimizer-analyses"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"
  attribute { name = "pk" type = "S" }
  attribute { name = "sk" type = "S" }
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
    Statement = [{ Effect = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action = "sts:AssumeRole" }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "ai-cost-optimizer-policy"
  role = aws_iam_role.lambda_role.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      { Effect = "Allow"
        Action = ["ce:GetCostAndUsage","ce:GetCostForecast","support:*"]
        Resource = "*" },
      { Effect = "Allow"
        Action = ["ec2:Describe*","cloudwatch:GetMetricStatistics",
                  "elasticloadbalancing:DescribeLoadBalancers"]
        Resource = "*" },
      { Effect = "Allow"
        Action = ["dynamodb:PutItem","dynamodb:GetItem","dynamodb:Scan","dynamodb:Query"]
        Resource = ["${aws_dynamodb_table.cost_data.arn}",
                    "${aws_dynamodb_table.waste_data.arn}",
                    "${aws_dynamodb_table.forecasts.arn}",
                    "${aws_dynamodb_table.analyses.arn}"] },
      { Effect = "Allow"
        Action = ["s3:PutObject","s3:GetObject"]
        Resource = "${aws_s3_bucket.reports.arn}/*" },
      { Effect = "Allow"
        Action = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.anthropic.arn },
      { Effect = "Allow"
        Action = ["ses:SendEmail"]  Resource = "*" },
      { Effect = "Allow"
        Action = ["lambda:InvokeFunction"]  Resource = "*" },
      { Effect = "Allow"
        Action = ["logs:CreateLogGroup","logs:CreateLogStream","logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*" }
    ]
  })
}

# ── Lambda: Cost Collector ───────────────────────────────────
resource "aws_lambda_function" "cost_collector" {
  filename      = "../lambdas/cost_collector.zip"
  function_name = "ai-cost-collector"
  role          = aws_iam_role.lambda_role.arn
  handler       = "handler.lambda_handler"
  runtime       = "python3.12"
  timeout       = 120
  memory_size   = 256
  environment {
    variables = { COST_TABLE = aws_dynamodb_table.cost_data.name }
  }
}

# (Repeat similar aws_lambda_function blocks for:
#  waste_detector, forecaster, claude_analyser, report_generator, alerter)

# ── EventBridge: Run daily at 08:00 UTC ──────────────────────
resource "aws_cloudwatch_event_rule" "daily_run" {
  name                = "ai-cost-optimizer-daily"
  schedule_expression = "cron(0 8 * * ? *)"
}

resource "aws_cloudwatch_event_target" "start_collector" {
  rule      = aws_cloudwatch_event_rule.daily_run.name
  target_id = "CostCollector"
  arn       = aws_lambda_function.cost_collector.arn
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cost_collector.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.daily_run.arn
}

# ── EventBridge: Weekly report on Mondays at 08:30 ───────────
resource "aws_cloudwatch_event_rule" "weekly_report" {
  name                = "ai-cost-optimizer-weekly"
  schedule_expression = "cron(30 8 ? * MON *)"
}
