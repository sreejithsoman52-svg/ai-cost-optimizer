import boto3
import json
import os
import logging
from datetime import datetime, timedelta
from decimal import Decimal

logger = logging.getLogger()
logger.setLevel(logging.INFO)

ec2    = boto3.client("ec2")
cw     = boto3.client("cloudwatch")
elb    = boto3.client("elbv2")
dynamo = boto3.resource("dynamodb")
table  = dynamo.Table(os.environ["WASTE_TABLE"])

def lambda_handler(event, context):
    """Find all wasted AWS resources and store findings in DynamoDB."""
    findings = []
    findings.extend(find_idle_ec2_instances())
    findings.extend(find_unattached_ebs_volumes())
    findings.extend(find_unattached_elastic_ips())
    findings.extend(find_idle_load_balancers())

    # Save all findings
    timestamp = datetime.utcnow().isoformat()
    for f in findings:
        table.put_item(Item={**f, "detected_at": timestamp})

    total_savings = sum(float(f.get("monthly_saving_usd", 0)) for f in findings)
    logger.info(f"Found {len(findings)} waste items. Potential saving: ${total_savings:.2f}/mo")
    return {"statusCode": 200, "findings": len(findings), "potential_saving": total_savings}


def get_average_cpu(instance_id, days=14):
    """Get average CPU % for an EC2 instance over the last N days."""
    resp = cw.get_metric_statistics(
        Namespace="AWS/EC2",
        MetricName="CPUUtilization",
        Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        StartTime=datetime.utcnow() - timedelta(days=days),
        EndTime=datetime.utcnow(),
        Period=86400,   # 1 day in seconds
        Statistics=["Average"]
    )
    datapoints = resp.get("Datapoints", [])
    if not datapoints:
        return 0
    return sum(d["Average"] for d in datapoints) / len(datapoints)


def find_idle_ec2_instances():
    """Flag EC2 instances running with less than 5% CPU for 14 days."""
    findings = []
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(Filters=[{"Name": "instance-state-name",
                                              "Values": ["running"]}]):
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:",
                iid   = inst["InstanceId"]
                itype = inst["InstanceType"]
                name  = next((t["Value"] for t in inst.get("Tags", [])
                              if t["Key"] == "Name"), iid)
                avg_cpu = get_average_cpu(iid)
                if avg_cpu < 5.0:
                    # Rough monthly cost estimate
                    cost_map = {"t3.micro":8,"t3.small":16,"t3.medium":30,
                                "t3.large":60,"m5.large":70,"m5.xlarge":140}
                    est_cost = cost_map.get(itype, 50)
                    findings.append({
                        "pk":          f"WASTE#{iid}",
                        "sk":          "EC2_IDLE",
                        "resource_id": iid,
                        "resource_name": name,
                        "type":        "EC2_IDLE",
                        "severity":    "High",
                        "avg_cpu_pct": Decimal(str(round(avg_cpu, 2))),
                        "instance_type": itype,
                        "monthly_saving_usd": Decimal(str(est_cost)),
                        "description": f"EC2 {iid} has only {avg_cpu:.1f}% avg CPU over 14 days",
                        "fix":         "Stop or terminate this instance if not needed",
                    })
    return findings


def find_unattached_ebs_volumes():
    """Flag EBS volumes that are not attached to any instance."""
    findings = []
    paginator = ec2.get_paginator("describe_volumes")
    for page in paginator.paginate(Filters=[{"Name":"status","Values":["available"]}]):
        for vol in page["Volumes"]:
            size_gb = vol["Size"]
            cost    = round(size_gb * 0.10, 2)   # $0.10/GB/month for gp2
            findings.append({
                "pk":          f"WASTE#{vol['VolumeId']}",
                "sk":          "EBS_UNATTACHED",
                "resource_id": vol["VolumeId"],
                "type":        "EBS_UNATTACHED",
                "severity":    "Medium",
                "size_gb":     size_gb,
                "monthly_saving_usd": Decimal(str(cost)),
                "description": f"EBS volume {vol['VolumeId']} ({size_gb} GB) not attached to any instance",
                "fix":         "Delete this volume if it is no longer needed. Take a snapshot first.",
            })
    return findings


def find_unattached_elastic_ips():
    """Flag Elastic IPs not associated with any resource."""
    findings = []
    resp = ec2.describe_addresses()
    for addr in resp.get("Addresses", []):
        if "AssociationId" not in addr:
            findings.append({
                "pk":          f"WASTE#{addr['AllocationId']}",
                "sk":          "EIP_UNATTACHED",
                "resource_id": addr["AllocationId"],
                "type":        "EIP_UNATTACHED",
                "severity":    "Low",
                "monthly_saving_usd": Decimal("3.60"),
                "description": f"Elastic IP {addr.get('PublicIp')} is not attached to anything",
                "fix":         "Release this Elastic IP in the EC2 console to stop paying for it.",
            })
    return findings


def find_idle_load_balancers():
    """Flag load balancers with near-zero request counts."""
    findings = []
    try:
        lbs = elb.describe_load_balancers().get("LoadBalancers", [])
        for lb in lbs:
            arn  = lb["LoadBalancerArn"]
            name = lb["LoadBalancerName"]
            resp = cw.get_metric_statistics(
                Namespace="AWS/ApplicationELB",
                MetricName="RequestCount",
                Dimensions=[{"Name":"LoadBalancer","Value":arn.split("/",1)[1]}],
                StartTime=datetime.utcnow()-timedelta(days=14),
                EndTime=datetime.utcnow(),
                Period=86400*14, Statistics=["Sum"]
            )
            total_requests = sum(d["Sum"] for d in resp.get("Datapoints",[]))
            if total_requests < 100:
                findings.append({
                    "pk":          f"WASTE#{arn}",
                    "sk":          "ELB_IDLE",
                    "resource_id": arn,
                    "resource_name": name,
                    "type":        "ELB_IDLE",
                    "severity":    "High",
                    "monthly_saving_usd": Decimal("18.00"),
                    "description": f"Load Balancer {name} handled only {int(total_requests)} requests in 14 days",
                    "fix":         "Delete this load balancer if it is no longer routing traffic.",
                })
    except Exception as e:
        logger.warning(f"ELB check failed: {e}")
    return findings
