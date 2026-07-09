import boto3
import json
import os
import logging
import urllib.request
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamo         = boto3.resource("dynamodb")
analysis_table = dynamo.Table(os.environ["ANALYSIS_TABLE"])
fore_table     = dynamo.Table(os.environ["FORECAST_TABLE"])
ses            = boto3.client("ses", region_name=os.environ.get("SES_REGION","eu-west-1"))
SENDER_EMAIL   = os.environ["SENDER_EMAIL"]
RECIPIENT_EMAIL = os.environ["RECIPIENT_EMAIL"]
SLACK_WEBHOOK  = os.environ.get("SLACK_WEBHOOK_URL","")
MONTHLY_BUDGET = float(os.environ.get("MONTHLY_BUDGET_USD","1000"))

def lambda_handler(event, context):
    """Send alerts if high severity waste found or budget exceeded."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # Get latest analysis
    resp     = analysis_table.get_item(Key={"pk":"ANALYSIS#LATEST","sk":today})
    item     = resp.get("Item",{})
    if not item: return {"statusCode":200,"body":"No analysis for today"}

    analysis      = json.loads(item.get("analysis","{}")) if item else {}
    severity      = analysis.get("severity_overall","Low")
    saving        = float(item.get("total_saving",0))
    forecast_item = fore_table.get_item(Key={"pk":"FORECAST#LATEST","sk":"30DAY"}).get("Item",{})
    forecast      = float(forecast_item.get("forecast_30day_usd", 0))
    headline      = analysis.get("one_line_headline","AWS cost optimisation findings ready")
    summary       = analysis.get("executive_summary","")
    actions       = analysis.get("priority_actions",[])

    # Decide whether to send alert
    should_alert = (
        severity in ["Critical","High"] or
        saving > 100 or
        forecast > MONTHLY_BUDGET
    )

    if not should_alert:
        logger.info(f"No alert needed. Severity: {severity}, Saving: ${saving:.2f}")
        return {"statusCode":200,"body":"No alert needed"}

    # Build email body
    actions_text = ""
    for a in actions[:3]:
        steps = chr(10).join(f"  {i+1}. {s}" for i,s in enumerate(a.get("steps_to_fix",[])[:3]))
        actions_text += f"""
ACTION {a['rank']}: {a.get('title','')}
{a.get('plain_english_explanation','')}
Monthly Saving: ${a.get('monthly_saving_usd',0):.2f} | Effort: {a.get('effort_to_fix','')}
Steps:
{steps}
"""

    email_body = f"""AWS Cloud Cost Optimisation Alert
{"="*50}
Date: {today}
Overall Severity: {severity}
Total Potential Monthly Saving: ${saving:.2f}

SUMMARY:
{summary}

TOP PRIORITY ACTIONS:
{actions_text}

View the full report in your S3 reports bucket.
"""

    # Send email via SES
    ses.send_email(
        Source=SENDER_EMAIL,
        Destination={"ToAddresses":[RECIPIENT_EMAIL]},
        Message={
            "Subject":{"Data":f"[{severity}] {headline}"},
            "Body":{"Text":{"Data":email_body}}
        }
    )
    logger.info("Email alert sent")

    # Send Slack message if configured
    if SLACK_WEBHOOK:
        payload = {"text":f"*[{severity}] AWS Cost Alert*\n{headline}\nPotential saving: *${saving:.2f}/month*"}
        req = urllib.request.Request(SLACK_WEBHOOK,
            data=json.dumps(payload).encode(),
            headers={"Content-Type":"application/json"}, method="POST")
        urllib.request.urlopen(req)
        logger.info("Slack alert sent")

    return {"statusCode":200,"body":"Alert sent"}

