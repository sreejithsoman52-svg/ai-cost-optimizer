import anthropic
import boto3
import json
import os
import logging
from datetime import datetime
from decimal import Decimal
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamo       = boto3.resource("dynamodb")
waste_table  = dynamo.Table(os.environ["WASTE_TABLE"])
fore_table   = dynamo.Table(os.environ["FORECAST_TABLE"])
analysis_table = dynamo.Table(os.environ["ANALYSIS_TABLE"])

def get_api_key():
    """Securely fetch Anthropic API key from Secrets Manager."""
    sm = boto3.client("secretsmanager")
    resp = sm.get_secret_value(SecretId=os.environ["SECRET_NAME"])
    return json.loads(resp["SecretString"])["api_key"]


def lambda_handler(event, context):
    """Fetch all waste findings + forecast, send to Claude, save analysis."""
    # ── Collect all waste findings from DynamoDB ───────────────
    scan_resp = waste_table.scan()
    findings  = scan_resp.get("Items", [])

    if not findings:
        logger.info("No waste findings to analyse.")
        return {"statusCode": 200, "body": "Nothing to analyse"}

    # ── Get latest forecast ────────────────────────────────────
    forecast_resp = fore_table.get_item(
        Key={"pk": "FORECAST#LATEST", "sk": "30DAY"}
    )
    forecast = forecast_resp.get("Item", {})

    # ── Convert Decimal to float for JSON serialisation ────────
    def dec_to_float(obj):
        if isinstance(obj, Decimal): return float(obj)
        if isinstance(obj, dict): return {k: dec_to_float(v) for k,v in obj.items()}
        if isinstance(obj, list): return [dec_to_float(i) for i in obj]
        return obj

    findings_clean  = dec_to_float(findings)
    forecast_clean  = dec_to_float(forecast)

    total_potential_saving = sum(f.get("monthly_saving_usd", 0) for f in findings_clean)

    # ── Build the Claude prompt ────────────────────────────────
    prompt = f"""
You are a senior AWS Cloud Financial Advisor (FinOps expert).
Your audience is a BEGINNER — someone who does not know AWS deeply.
Write everything in simple, clear language. No jargon without explanation.

WASTE FINDINGS DETECTED IN THIS AWS ACCOUNT:
{json.dumps(findings_clean, indent=2)}

COST FORECAST:
{json.dumps(forecast_clean, indent=2)}

TOTAL POTENTIAL MONTHLY SAVING: ${total_potential_saving:.2f}

Generate a JSON analysis with EXACTLY these fields:
{{
  "executive_summary": "3-4 sentences. What is the overall situation? How bad is the waste? What is the biggest opportunity?",
  "severity_overall": "Critical | High | Medium | Low",
  "priority_actions": [
    {{
      "rank": 1,
      "title": "Short title of the action",
      "plain_english_explanation": "Explain in 2-3 sentences what this waste is. Use an everyday analogy if helpful.",
      "monthly_saving_usd": 0.0,
      "effort_to_fix": "5 minutes | 30 minutes | 1 hour | Half a day",
      "steps_to_fix": ["Step 1", "Step 2", "Step 3"]
    }}
  ],
  "forecast_commentary": "2-3 sentences explaining what the forecast means. Is the bill going up or down? Should they be worried?",
  "quick_wins": ["Action 1 that takes under 10 minutes", "Action 2"],
  "prevention_tips": ["Tip 1 to avoid this waste in future", "Tip 2"],
  "monthly_saving_if_all_fixed": {total_potential_saving:.2f},
  "annual_saving_if_all_fixed": {total_potential_saving * 12:.2f},
  "one_line_headline": "Single sentence headline suitable for an email subject line"
}}

Return ONLY the JSON. No markdown, no explanation outside the JSON.
"""

    # ── Call Claude API ────────────────────────────────────────
    client  = anthropic.Anthropic(api_key=get_api_key())
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=4096,
        system=(
            "You are an expert AWS FinOps advisor writing for beginners. "
            "Always return valid JSON. Use simple language. Be specific and actionable."
        ),
        messages=[{"role": "user", "content": prompt}]
    )

    raw      = message.content[0].text.strip().replace("```json","").replace("```","")
    analysis = json.loads(raw)

    # ── Save analysis to DynamoDB ──────────────────────────────
    analysis_table.put_item(Item={
        "pk":           "ANALYSIS#LATEST",
        "sk":           datetime.utcnow().strftime("%Y-%m-%d"),
        "analysis":     json.dumps(analysis),
        "generated_at": datetime.utcnow().isoformat(),
        "findings_count": len(findings),
        "total_saving": str(round(total_potential_saving, 2))
    })

    logger.info(f"Analysis complete. Severity: {analysis.get('severity_overall')} | Saving: ${total_potential_saving:.2f}/mo")
    return {"statusCode": 200, "severity": analysis.get("severity_overall"),
            "potential_saving": total_potential_saving}
