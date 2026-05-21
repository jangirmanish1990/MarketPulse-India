"""AWS component smoke-test for Day 3.

Verifies that all MarketPulse AWS resources are correctly provisioned:
  - S3 bucket exists and accepts a PutObject
  - DynamoDB tables (nse-poll-state, nse-watched-symbols) exist
  - Lambda function (marketpulse-nse-poller) is deployed and Active
  - EventBridge rule (marketpulse-nse-poller-schedule) is ENABLED

Usage:
    python scripts/test_aws.py [--region ap-south-1]

Prints:  AWS Day 3 PASSED  or  AWS Day 3 FAILED
Exit code 0 on pass, 1 on failure.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3
from botocore.exceptions import ClientError

IST = ZoneInfo("Asia/Kolkata")

BUCKET_NAME = "marketpulse-india-filings"
POLL_STATE_TABLE = "nse-poll-state"
SYMBOLS_TABLE = "nse-watched-symbols"
LAMBDA_FUNCTION = "marketpulse-nse-poller"
EB_RULE_NAME = "marketpulse-nse-poller-schedule"

SEP = "=" * 56
OK = "[PASS]"
FAIL = "[FAIL]"


def _check(label: str, ok: bool, detail: str = "") -> bool:
    status = OK if ok else FAIL
    suffix = f"  {detail}" if detail else ""
    print(f"  {status}  {label}{suffix}")
    return ok


def test_s3(region: str) -> bool:
    s3 = boto3.client("s3", region_name=region)
    results: list[bool] = []

    # bucket accessible
    try:
        s3.head_bucket(Bucket=BUCKET_NAME)
        results.append(_check(f"S3 bucket '{BUCKET_NAME}' exists", True))
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        results.append(_check(f"S3 bucket '{BUCKET_NAME}' exists", False, f"HTTP {code}"))
        return False  # no point testing PutObject if bucket missing

    # write a test object
    test_key = f"_test/smoke-{datetime.now(IST).strftime('%Y%m%dT%H%M%S')}.json"
    try:
        s3.put_object(
            Bucket=BUCKET_NAME,
            Key=test_key,
            Body=json.dumps({"smoke_test": True, "ts": datetime.now(IST).isoformat()}),
            ContentType="application/json",
        )
        results.append(_check("S3 PutObject succeeds", True, test_key))
    except ClientError as exc:
        results.append(_check("S3 PutObject succeeds", False, str(exc)))

    return all(results)


def test_dynamodb(region: str) -> bool:
    dynamo = boto3.client("dynamodb", region_name=region)
    results: list[bool] = []

    for table_name in (POLL_STATE_TABLE, SYMBOLS_TABLE):
        try:
            resp = dynamo.describe_table(TableName=table_name)
            status = resp["Table"]["TableStatus"]
            results.append(_check(f"DynamoDB '{table_name}'", status == "ACTIVE", status))
        except ClientError as exc:
            results.append(_check(f"DynamoDB '{table_name}'", False, str(exc)))

    return all(results)


def test_lambda(region: str) -> bool:
    lmb = boto3.client("lambda", region_name=region)
    results: list[bool] = []

    try:
        resp = lmb.get_function(FunctionName=LAMBDA_FUNCTION)
        state = resp["Configuration"]["State"]
        runtime = resp["Configuration"]["Runtime"]
        mem = resp["Configuration"]["MemorySize"]
        timeout = resp["Configuration"]["Timeout"]
        results.append(_check(
            f"Lambda '{LAMBDA_FUNCTION}' deployed",
            state == "Active",
            f"{state} runtime={runtime} mem={mem}MB timeout={timeout}s",
        ))
    except ClientError as exc:
        results.append(_check(f"Lambda '{LAMBDA_FUNCTION}' deployed", False, str(exc)))
        return False

    # verify env vars present
    env = resp["Configuration"].get("Environment", {}).get("Variables", {})
    for var in ("FASTAPI_WEBHOOK_URL", "WEBHOOK_SECRET", "NSE_POLL_STATE_TABLE", "S3_BUCKET"):
        results.append(_check(f"Lambda env var {var}", var in env))

    return all(results)


def test_eventbridge(region: str) -> bool:
    eb = boto3.client("events", region_name=region)
    results: list[bool] = []

    try:
        resp = eb.describe_rule(Name=EB_RULE_NAME)
        state = resp.get("State", "UNKNOWN")
        schedule = resp.get("ScheduleExpression", "")
        results.append(_check(
            f"EventBridge rule '{EB_RULE_NAME}'",
            state == "ENABLED",
            f"{state}  schedule={schedule}",
        ))
    except ClientError as exc:
        results.append(_check(f"EventBridge rule '{EB_RULE_NAME}'", False, str(exc)))

    return all(results)


def main() -> None:
    parser = argparse.ArgumentParser(description="MarketPulse AWS Day 3 smoke-test")
    parser.add_argument("--region", default="ap-south-1")
    args = parser.parse_args()
    region: str = args.region

    print(SEP)
    print(f"MarketPulse AWS smoke-test  (region={region})")
    print(f"Run at: {datetime.now(IST).isoformat()} IST")
    print(SEP)

    sections: dict[str, bool] = {}

    print("\nS3")
    sections["S3"] = test_s3(region)

    print("\nDynamoDB")
    sections["DynamoDB"] = test_dynamodb(region)

    print("\nLambda")
    sections["Lambda"] = test_lambda(region)

    print("\nEventBridge")
    sections["EventBridge"] = test_eventbridge(region)

    print(f"\n{SEP}")
    overall = all(sections.values())
    for name, ok in sections.items():
        print(f"  {OK if ok else FAIL}  {name}")
    print(SEP)

    if overall:
        print("AWS Day 3 PASSED")
    else:
        print("AWS Day 3 FAILED")

    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
