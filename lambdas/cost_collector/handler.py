import boto3
import json
import os
import logging
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ce     = boto3.client("ce", region_name="us-east-1")   # Cost Explorer
dynamo = boto3.resource("dynamodb")
table  = dynamo.Table(os.environ["COST_TABLE"])

def lambda_handler(event, context):
    """Runs every morning. Collects cost data and stores it in DynamoDB."""
    try:
        today     = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        start     = str(today - timedelta(days=90))   # 90 days of history
        end       = str(today)

        logger.info(f"Collecting costs from {start} to {end}")

        # ── Get daily costs split by AWS service ──────────────
        response = ce.get_cost_and_usage(
            TimePeriod={"Start": start, "End": end},
            Granularity="DAILY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}]
        )

        # ── Save each day's data to DynamoDB ──────────────────
        saved_count = 0
        for result in response["ResultsByTime"][:90]:
            date_str = result["TimePeriod"]["Start"]
            for group in result.get("Groups", []):
                service = group["Keys"][0]
                amount  = float(group["Metrics"]["UnblendedCost"]["Amount"])
                if amount > 0:
                    table.put_item(Item={
                        "pk":      f"COST#{date_str}",
                        "sk":      f"SERVICE#{service}",
                        "date":    date_str,
                        "service": service,
                        "amount":  Decimal(str(round(amount, 4))),
                        "ttl":     int((datetime.utcnow() + timedelta(days=365)).timestamp())
                    })
                    saved_count += 1

        # ── Also get overall monthly total ────────────────────
        month_start = str(today.replace(day=1))
        monthly = ce.get_cost_and_usage(
            TimePeriod={"Start": month_start, "End": end},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"]
        )
        month_total = float(
            monthly["ResultsByTime"][0]["Total"]["UnblendedCost"]["Amount"]
        )
        table.put_item(Item={
            "pk":          f"MONTHLY#{str(today.replace(day=1))}",
            "sk":          "TOTAL",
            "month":       month_start,
            "total_spend": Decimal(str(round(month_total, 2))),
        })

        logger.info(f"Saved {saved_count} records. Month-to-date: ${month_total:.2f}")
        return {"statusCode": 200, "body": f"Saved {saved_count} cost records"}

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        raise
