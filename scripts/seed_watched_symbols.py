"""Seed nse-watched-symbols DynamoDB table with top-10 NSE symbols.

Usage:
    python scripts/seed_watched_symbols.py [--table nse-watched-symbols] [--region ap-south-1]

Requires boto3 and valid AWS credentials (env vars or ~/.aws/credentials).
Safe to run multiple times — uses put_item which upserts.
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import boto3

IST = ZoneInfo("Asia/Kolkata")

TOP_10_SYMBOLS = [
    "RELIANCE",
    "TCS",
    "INFY",
    "HDFCBANK",
    "ICICIBANK",
    "WIPRO",
    "BAJFINANCE",
    "TITAN",
    "NESTLEIND",
    "SUNPHARMA",
]


def seed(table_name: str, region: str) -> None:
    dynamodb = boto3.resource("dynamodb", region_name=region)
    table = dynamodb.Table(table_name)
    added_at = datetime.now(IST).isoformat()

    print(f"Seeding {len(TOP_10_SYMBOLS)} symbols into {table_name} ({region})...")
    for symbol in TOP_10_SYMBOLS:
        table.put_item(
            Item={
                "nse_symbol": symbol,
                "is_active": True,
                "added_at": added_at,
            }
        )
        print(f"  + {symbol}")

    print(f"\nDone — {len(TOP_10_SYMBOLS)} symbols seeded.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed NSE watched-symbols table")
    parser.add_argument("--table", default="nse-watched-symbols")
    parser.add_argument("--region", default="ap-south-1")
    args = parser.parse_args()

    try:
        seed(args.table, args.region)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
