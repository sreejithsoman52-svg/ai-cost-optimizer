#!/usr/bin/env python3
"""
Seed the deployed DynamoDB tables with realistic dummy data, so you can
demo the pipeline (reports, alerts, dashboard) without waiting for a
real 90-day AWS cost history or real idle resources to accumulate.

Run this AFTER `terraform apply` has created the tables, from the EC2
instance (or anywhere with AWS credentials that can reach the tables).

Usage:
    python3 seed_demo_data.py
    python3 seed_demo_data.py --cost-table my-costs --waste-table my-waste ...

Defaults match the table names produced by terraform/main.tf.
"""
import argparse
import json
import random
from datetime import datetime, timedelta, date, timezone
from decimal import Decimal

import boto3


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--region", default="eu-central-1")
    p.add_argument("--cost-table", default="ai-cost-optimizer-costs")
    p.add_argument("--waste-table", default="ai-cost-optimizer-waste")
    p.add_argument("--forecast-table", default="ai-cost-optimizer-forecasts")
    p.add_argument("--analysis-table", default="ai-cost-optimizer-analyses")
    p.add_argument("--days", type=int, default=90, help="days of dummy cost history")
    return p.parse_args()


def seed_cost_history(table, days):
    """90 days of daily cost split across 4 services, gentle upward drift."""
    today = date.today()
    services = ["Amazon EC2", "Amazon EBS", "Amazon S3", "AWS Lambda"]
    base = 22.0
    count = 0
    with table.batch_writer() as batch:
        for d in range(days, 0, -1):
            day = today - timedelta(days=d)
            drift = (days - d) * 0.18
            for svc in services:
                amt = max(0.5, base * random.uniform(0.85, 1.15) / len(services)
                          + drift / len(services))
                batch.put_item(Item={
                    "pk": f"COST#{day}",
                    "sk": f"SERVICE#{svc}",
                    "date": str(day),
                    "service": svc,
                    "amount": Decimal(str(round(amt, 4))),
                    "ttl": int((datetime.now(timezone.utc) + timedelta(days=365)).timestamp()),
                })
                count += 1
    print(f"  cost_table: wrote {count} daily cost records ({days} days x {len(services)} services)")


def seed_waste_findings(table):
    """5 representative waste findings, matching what waste_detector.py produces."""
    now = datetime.now(timezone.utc).isoformat()
    findings = [
        {"pk": "WASTE#i-demo0001", "sk": "EC2_IDLE", "resource_id": "i-demo0001",
         "resource_name": "demo-idle-app-01", "type": "EC2_IDLE", "severity": "High",
         "avg_cpu_pct": Decimal("1.4"), "instance_type": "t3.medium",
         "monthly_saving_usd": Decimal("30.00"),
         "description": "EC2 i-demo0001 has only 1.4% avg CPU over 14 days",
         "fix": "Stop or terminate this instance if not needed", "detected_at": now},
        {"pk": "WASTE#i-demo0002", "sk": "EC2_IDLE", "resource_id": "i-demo0002",
         "resource_name": "demo-idle-app-02", "type": "EC2_IDLE", "severity": "High",
         "avg_cpu_pct": Decimal("0.9"), "instance_type": "t3.medium",
         "monthly_saving_usd": Decimal("30.00"),
         "description": "EC2 i-demo0002 has only 0.9% avg CPU over 14 days",
         "fix": "Stop or terminate this instance if not needed", "detected_at": now},
        {"pk": "WASTE#vol-demo0001", "sk": "EBS_UNATTACHED", "resource_id": "vol-demo0001",
         "type": "EBS_UNATTACHED", "severity": "Medium", "size_gb": 250,
         "monthly_saving_usd": Decimal("25.00"),
         "description": "EBS volume vol-demo0001 (250 GB) not attached to any instance",
         "fix": "Delete this volume if it is no longer needed. Take a snapshot first.",
         "detected_at": now},
        {"pk": "WASTE#vol-demo0002", "sk": "EBS_UNATTACHED", "resource_id": "vol-demo0002",
         "type": "EBS_UNATTACHED", "severity": "Medium", "size_gb": 100,
         "monthly_saving_usd": Decimal("10.00"),
         "description": "EBS volume vol-demo0002 (100 GB) not attached to any instance",
         "fix": "Delete this volume if it is no longer needed. Take a snapshot first.",
         "detected_at": now},
        {"pk": "WASTE#eipalloc-demo0001", "sk": "EIP_UNATTACHED",
         "resource_id": "eipalloc-demo0001", "type": "EIP_UNATTACHED", "severity": "Low",
         "monthly_saving_usd": Decimal("3.60"),
         "description": "Elastic IP 198.51.100.42 is not attached to anything",
         "fix": "Release this Elastic IP in the EC2 console to stop paying for it.",
         "detected_at": now},
    ]
    with table.batch_writer() as batch:
        for item in findings:
            batch.put_item(Item=item)
    print(f"  waste_table: wrote {len(findings)} findings")
    return findings


def seed_forecast(table, daily_avg=29.76, trend="stable", data_points=90):
    forecast_30day = round(daily_avg * 30 * 1.15, 2)
    item = {
        "pk": "FORECAST#LATEST",
        "sk": "30DAY",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "forecast_30day_usd": Decimal(str(forecast_30day)),
        "trend": trend,
        "daily_avg_usd": Decimal(str(daily_avg)),
        "trend_slope": Decimal("0.18"),
        "pct_change_estimate": Decimal("6.1"),
        "data_points_used": data_points,
    }
    table.put_item(Item=item)
    print(f"  forecast_table: wrote 1 forecast (${forecast_30day}/30 days, trend={trend})")
    return item


def seed_analysis(table, findings, forecast):
    total_saving = round(sum(float(f["monthly_saving_usd"]) for f in findings), 2)
    analysis = {
        "executive_summary": (
            f"This AWS account currently has {len(findings)} waste item(s) totalling "
            f"${total_saving:.2f}/month in avoidable spend. Two high-severity idle EC2 "
            f"instances are the biggest opportunity. The 30-day cost forecast is trending "
            f"{forecast['trend']}, so acting on these findings now will meaningfully change "
            f"next month's bill."
        ),
        "severity_overall": "High",
        "priority_actions": [
            {"rank": 1, "title": "Stop idle EC2 instance demo-idle-app-01",
             "plain_english_explanation": "This server has been running at ~1% CPU for two weeks. "
                                            "This is like paying rent on an empty apartment.",
             "monthly_saving_usd": 30.0, "effort_to_fix": "5 minutes",
             "steps_to_fix": ["Stop or terminate the instance if not needed",
                               "Confirm in the AWS console before deleting anything.",
                               "Re-check next week's report to confirm the saving appeared."]},
            {"rank": 2, "title": "Stop idle EC2 instance demo-idle-app-02",
             "plain_english_explanation": "Same pattern as above — near-zero usage for two weeks.",
             "monthly_saving_usd": 30.0, "effort_to_fix": "5 minutes",
             "steps_to_fix": ["Stop or terminate the instance if not needed",
                               "Confirm in the AWS console before deleting anything.",
                               "Re-check next week's report to confirm the saving appeared."]},
            {"rank": 3, "title": "Delete unattached 250GB EBS volume",
             "plain_english_explanation": "This is like paying a storage unit fee for a box you "
                                            "don't own anymore.",
             "monthly_saving_usd": 25.0, "effort_to_fix": "30 minutes",
             "steps_to_fix": ["Take a snapshot if unsure, then delete the volume",
                               "Confirm in the AWS console before deleting anything.",
                               "Re-check next week's report to confirm the saving appeared."]},
        ],
        "forecast_commentary": (
            f"Based on the last {forecast['data_points_used']} days, spend is "
            f"{forecast['trend']} at roughly ${float(forecast['daily_avg_usd']):.2f}/day. "
            f"The model projects about ${float(forecast['forecast_30day_usd']):.2f} over the "
            f"next 30 days if nothing changes."
        ),
        "quick_wins": ["Release the unattached Elastic IP — takes under 5 minutes"],
        "prevention_tips": [
            "Tag every EC2 instance with an owner so idle ones are easy to trace back to a team.",
            "Set a CloudWatch alarm on low CPU utilisation so idle instances are caught within days.",
        ],
        "monthly_saving_if_all_fixed": total_saving,
        "annual_saving_if_all_fixed": round(total_saving * 12, 2),
        "one_line_headline": f"${total_saving:.2f}/month in AWS waste found across {len(findings)} resources",
    }
    table.put_item(Item={
        "pk": "ANALYSIS#LATEST",
        "sk": str(date.today()),
        "analysis": json.dumps(analysis),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "findings_count": len(findings),
        "total_saving": str(total_saving),
    })
    print(f"  analysis_table: wrote 1 analysis (severity=High, saving=${total_saving})")


def main():
    args = parse_args()
    dynamo = boto3.resource("dynamodb", region_name=args.region)

    print(f"Seeding demo data into region {args.region} ...")
    cost_table = dynamo.Table(args.cost_table)
    waste_table = dynamo.Table(args.waste_table)
    forecast_table = dynamo.Table(args.forecast_table)
    analysis_table = dynamo.Table(args.analysis_table)

    seed_cost_history(cost_table, args.days)
    findings = seed_waste_findings(waste_table)
    forecast = seed_forecast(forecast_table)
    seed_analysis(analysis_table, findings, forecast)

    print("\nDone. You can now:")
    print(f"  - invoke the report_generator Lambda to build the demo HTML report")
    print(f"  - invoke the alerter Lambda to send the demo email/Slack alert")
    print(f"  - or just query the tables directly to show the raw data in the demo")


if __name__ == "__main__":
    main()
