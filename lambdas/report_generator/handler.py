import boto3
import json
import os
import logging
from datetime import datetime
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamo         = boto3.resource("dynamodb")
analysis_table = dynamo.Table(os.environ["ANALYSIS_TABLE"])
waste_table    = dynamo.Table(os.environ["WASTE_TABLE"])
s3             = boto3.client("s3")
BUCKET         = os.environ["REPORT_BUCKET"]

def lambda_handler(event, context):
    """Build a weekly HTML report and save it to S3."""
    today = datetime.utcnow().strftime("%Y-%m-%d")

    # ── Fetch the latest AI analysis ──────────────────────────
    resp     = analysis_table.get_item(Key={"pk":"ANALYSIS#LATEST","sk":today})
    item     = resp.get("Item",{})
    if not item:
        # Try yesterday's if today's not ready yet
        from datetime import timedelta
        yday = (datetime.utcnow()-timedelta(days=1)).strftime("%Y-%m-%d")
        resp = analysis_table.get_item(Key={"pk":"ANALYSIS#LATEST","sk":yday})
        item = resp.get("Item",{})

    analysis = json.loads(item.get("analysis","{}")) if item else {}

    # ── Fetch waste findings ───────────────────────────────────
    findings = waste_table.scan().get("Items",[])
    for f in findings:
        for k,v in f.items():
            if isinstance(v, Decimal): f[k] = float(v)

    total_saving = sum(f.get("monthly_saving_usd",0) for f in findings)

    # ── Build HTML report ──────────────────────────────────────
    html = build_html_report(analysis, findings, total_saving, today)

    # ── Save to S3 ─────────────────────────────────────────────
    report_key = f"reports/{today}/cost_optimization_report.html"
    s3.put_object(Bucket=BUCKET, Key=report_key,
                  Body=html.encode("utf-8"), ContentType="text/html")

    # Also save JSON for downstream use
    json_key = f"reports/{today}/cost_optimization_data.json"
    s3.put_object(Bucket=BUCKET, Key=json_key,
                  Body=json.dumps({"analysis":analysis,"findings":findings,"total_saving":total_saving}).encode(),
                  ContentType="application/json")

    logger.info(f"Report saved: s3://{BUCKET}/{report_key}")
    return {"statusCode":200, "report": f"s3://{BUCKET}/{report_key}"}


def build_html_report(analysis, findings, total_saving, date_str):
    """Build a clean HTML report page."""
    actions_html = ""
    for action in analysis.get("priority_actions",[])[:5]:
        steps = "".join(f"<li>{s}</li>" for s in action.get("steps_to_fix",[]))
        actions_html += f"""
        <div class="action-card">
          <h3>#{action['rank']} {action.get('title','')}</h3>
          <p>{action.get('plain_english_explanation','')}</p>
          <div class="saving">Save ${action.get('monthly_saving_usd',0):.2f}/month
          | Effort: {action.get('effort_to_fix','Unknown')}</div>
          <ol>{steps}</ol>
        </div>"""

    return f"""<!DOCTYPE html><html><head><meta charset="utf-8">
    <title>AWS Cost Optimisation Report – {date_str}</title>
    <style>
      body{{font-family:Arial,sans-serif;max-width:960px;margin:0 auto;padding:2rem;color:#333}}
      h1{{color:#1F3864}} h2{{color:#2E75B6}} .metric{{display:inline-block;
      background:#E1F5EE;border-radius:8px;padding:1rem 2rem;margin:0.5rem;text-align:center}}
      .metric .value{{font-size:2rem;font-weight:bold;color:#0F6E56}}
      .action-card{{border:1px solid #ddd;border-radius:8px;padding:1.5rem;margin:1rem 0}}
      .saving{{background:#FAEEDA;padding:0.5rem 1rem;border-radius:4px;margin:0.5rem 0}}
      table{{width:100%;border-collapse:collapse}}
      th{{background:#1F3864;color:white;padding:0.5rem}}
      td{{border:1px solid #ddd;padding:0.5rem}}tr:nth-child(even){{background:#f9f9f9}}
    </style></head><body>
    <h1>AWS Cost Optimisation Report</h1>
    <p>Generated: {date_str} | Powered by Claude AI</p>
    <h2>At a Glance</h2>
    <div class="metric"><div class="value">{len(findings)}</div>Waste Items Found</div>
    <div class="metric"><div class="value">${total_saving:.0f}/mo</div>Potential Monthly Saving</div>
    <div class="metric"><div class="value">${total_saving*12:.0f}/yr</div>Potential Annual Saving</div>
    <h2>AI Summary</h2><p>{analysis.get("executive_summary","Analysis not available")}</p>
    <p><strong>Forecast:</strong> {analysis.get("forecast_commentary","")}</p>
    <h2>Priority Actions</h2>{actions_html}
    <h2>All Waste Findings</h2>
    <table><tr><th>Resource ID</th><th>Type</th><th>Severity</th>
    <th>Monthly Saving</th><th>Fix</th></tr>
    {"".join(f'<tr><td>{f.get("resource_id","")}</td><td>{f.get("type","")}</td>'
    f'<td>{f.get("severity","")}</td><td>${float(f.get("monthly_saving_usd",0)):.2f}</td>'
    f'<td>{f.get("fix","")}</td></tr>' for f in findings)}
    </table></body></html>"""

