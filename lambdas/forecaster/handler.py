import boto3
import os
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from collections import defaultdict

logger = logging.getLogger()
logger.setLevel(logging.INFO)

dynamo      = boto3.resource("dynamodb")
cost_table  = dynamo.Table(os.environ["COST_TABLE"])
fore_table  = dynamo.Table(os.environ["FORECAST_TABLE"])

def lambda_handler(event, context):
    """Read 90 days of history and produce a 30-day cost forecast."""
    # Read daily totals from DynamoDB
    daily_totals = get_daily_totals(days=90)

    if len(daily_totals) < 7:
        logger.warning("Not enough data for forecast (need at least 7 days)")
        return {"statusCode": 200, "body": "Insufficient data"}

    # Simple linear regression to detect trend
    n          = len(daily_totals)
    x_vals     = list(range(n))
    y_vals     = daily_totals
    x_mean     = sum(x_vals) / n
    y_mean     = sum(y_vals) / n
    numerator   = sum((x-x_mean)*(y-y_mean) for x,y in zip(x_vals,y_vals))
    denominator = sum((x-x_mean)**2 for x in x_vals)
    slope       = numerator / denominator if denominator != 0 else 0

    # Project 30 days forward
    last_value     = daily_totals[-1]
    forecast_30day = max(0, last_value + slope * 30) * 30
    trend_direction = "increasing" if slope > 0.5 else "decreasing" if slope < -0.5 else "stable"
    pct_change = (slope * 30 / y_mean * 100) if y_mean else 0

    forecast = {
        "pk":                "FORECAST#LATEST",
        "sk":                "30DAY",
        "generated_at":     datetime.utcnow().isoformat(),
        "forecast_30day_usd": Decimal(str(round(forecast_30day, 2))),
        "trend":            trend_direction,
        "daily_avg_usd":    Decimal(str(round(y_mean, 2))),
        "trend_slope":      Decimal(str(round(slope, 4))),
        "pct_change_estimate": Decimal(str(round(pct_change, 1))),
        "data_points_used": n,
    }
    fore_table.put_item(Item=forecast)

    logger.info(f"Forecast: ${forecast_30day:.2f}/month | Trend: {trend_direction} | Change: {pct_change:.1f}%")
    return {"statusCode": 200, "forecast": float(forecast_30day), "trend": trend_direction}


def get_daily_totals(days=90):
    """Sum all service costs per day and return as a list of daily totals."""
    from boto3.dynamodb.conditions import Key
    today = datetime.utcnow().date()
    daily_sums = defaultdict(float)
    for d in range(days):
        date_str = str(today - timedelta(days=d))
        resp = cost_table.query(KeyConditionExpression=Key("pk").eq(f"COST#{date_str}"))
        for item in resp.get("Items", []):
            daily_sums[date_str] += float(item.get("amount", 0))
    return [daily_sums[str(today-timedelta(days=i))] for i in range(days-1,-1,-1)]
