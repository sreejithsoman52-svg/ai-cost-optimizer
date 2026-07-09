# AI-Powered AWS Cloud Cost Optimisation

Automated daily pipeline that finds wasted AWS spend, forecasts your bill,
uses Claude to turn the findings into a plain-English report, and emails
you a weekly summary.

## What's inside

| Lambda              | Runs           | Does |
|----------------------|----------------|------|
| `cost_collector`     | daily 08:00    | Pulls Cost Explorer data → DynamoDB |
| `waste_detector`      | daily 08:05    | Finds idle EC2, orphaned EBS/EIPs, idle load balancers |
| `bill_forecaster`     | daily 08:10    | Linear-trend 30-day cost forecast |
| `claude_analyser`     | daily 08:15    | Sends findings to Claude, gets back a structured JSON analysis |
| `report_generator`    | weekly Mon 08:30 | Builds an HTML report → S3 |
| `alerter`              | daily 08:25    | Emails/Slacks an alert if severity is high or budget is exceeded |

Everything here is the corrected version of the original plan — see
`docs/FIXES.md` for exactly what was wrong and what changed.

## 1. Get this onto GitHub

```bash
cd ai-cost-optimizer
git init
git add .
git commit -m "Initial commit: AI cost optimiser"
git branch -M main
git remote add origin https://github.com/<you>/ai-cost-optimizer.git
git push -u origin main
```

`terraform.tfvars` and `*.zip` build artifacts are already git-ignored —
nothing secret gets committed.

## 2. Clone onto an EC2 instance whenever you need to run it

```bash
git clone https://github.com/<you>/ai-cost-optimizer.git
cd ai-cost-optimizer
bash scripts/ec2_bootstrap.sh      # installs terraform, python, zip
```

The EC2 instance's IAM role (or your AWS CLI credentials) needs
permissions for: DynamoDB, S3, Lambda, IAM, Secrets Manager, SES,
EventBridge, EC2 (read), CloudWatch (read), Cost Explorer (read).

## 3. Configure

```bash
cp terraform/terraform.tfvars.example terraform/terraform.tfvars
# edit terraform.tfvars: bucket name, your Anthropic API key, sender/recipient email
```

## 4. Build and deploy

```bash
bash scripts/build_all.sh          # zips each Lambda with its dependencies
cd terraform
terraform init
terraform apply
```

After `apply`, AWS emails a verification link to `sender_email` — click
it before the Alerter can send anything (SES requirement).

## 5. Populate demo data (no need to wait for real usage/history)

```bash
python3 scripts/seed_demo_data.py \
    --region eu-central-1 \
    --cost-table ai-cost-optimizer-costs \
    --waste-table ai-cost-optimizer-waste \
    --forecast-table ai-cost-optimizer-forecasts \
    --analysis-table ai-cost-optimizer-analyses
```

(Table names above are the Terraform defaults — omit the flags if you
didn't change them.)

This writes 90 days of synthetic cost history, 5 representative waste
findings ($98.60/month total), a forecast, and a Claude-style analysis
directly into the deployed tables.

Then, to produce an actual demo report/email from that seeded data,
invoke the two downstream Lambdas directly:

```bash
aws lambda invoke --function-name ai-report-generator /tmp/out.json
aws lambda invoke --function-name ai-cost-alerter /tmp/out2.json
```

The report lands in your S3 reports bucket; the alert email goes to
`recipient_email`.

## 6. Tear down when you're done demoing

```bash
cd terraform
terraform destroy
```

## Repo layout

```
ai-cost-optimizer/
├── lambdas/
│   ├── cost_collector/{handler.py, requirements.txt}
│   ├── waste_detector/{handler.py, requirements.txt}
│   ├── bill_forecaster/{handler.py, requirements.txt}
│   ├── claude_analyser/{handler.py, requirements.txt}
│   ├── report_generator/{handler.py, requirements.txt}
│   └── alerter/{handler.py, requirements.txt}
├── terraform/
│   ├── main.tf
│   ├── variables.tf
│   ├── outputs.tf
│   └── terraform.tfvars.example
├── scripts/
│   ├── build_all.sh
│   ├── ec2_bootstrap.sh
│   └── seed_demo_data.py
└── docs/
    └── FIXES.md
```
