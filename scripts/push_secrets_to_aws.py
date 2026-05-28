"""scripts/push_secrets_to_aws.py

Reads .env values and pushes them to AWS Secrets Manager as a single
JSON secret named "marketpulse-india/prod".

Usage:
    python scripts/push_secrets_to_aws.py           # dry run (safe default)
    python scripts/push_secrets_to_aws.py --push    # write to AWS

Security rules:
  - Key *names* are always printed; secret *values* are never logged.
  - --push requires AWS credentials in the environment (or ~/.aws/credentials).
  - Only non-empty values are included in the secret payload.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"

SECRET_NAME = "marketpulse-india/prod"
AWS_REGION  = "ap-south-1"

SECRETS_TO_PUSH = [
    "DATABASE_URL",
    "JWT_SECRET_KEY",
    "WHATSAPP_ACCESS_TOKEN",
    "WHATSAPP_PHONE_NUMBER_ID",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "ALERT_SMS_NUMBER",
    "LANGCHAIN_API_KEY",
]

SEP = "-" * 42


def _load_env() -> dict[str, str]:
    """Load .env with python-dotenv; fall back to os.environ if file missing."""
    try:
        from dotenv import dotenv_values  # type: ignore[import-untyped]
        values = dict(dotenv_values(ENV_FILE))
    except ImportError:
        values = {}

    # Fill any gaps from the actual environment (e.g. in CI)
    for key in SECRETS_TO_PUSH:
        if key not in values and os.environ.get(key):
            values[key] = os.environ[key]

    return values


def _build_payload(env: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    """Return (payload_with_values, missing_keys)."""
    payload: dict[str, str] = {}
    missing: list[str] = []
    for key in SECRETS_TO_PUSH:
        val = env.get(key, "").strip()
        if val:
            payload[key] = val
        else:
            missing.append(key)
    return payload, missing


def _push_to_aws(payload: dict[str, str]) -> str:
    """Create or update the secret. Returns 'created' or 'updated'."""
    try:
        import boto3  # type: ignore[import-untyped]
    except ImportError:
        raise RuntimeError(
            "boto3 is not installed. Run: pip install boto3"
        ) from None

    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    secret_string = json.dumps(payload)

    try:
        client.create_secret(
            Name=SECRET_NAME,
            Description="MarketPulse India production secrets",
            SecretString=secret_string,
        )
        return "created"
    except client.exceptions.ResourceExistsException:
        client.update_secret(
            SecretId=SECRET_NAME,
            SecretString=secret_string,
        )
        return "updated"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Push .env secrets to AWS Secrets Manager."
    )
    parser.add_argument(
        "--push",
        action="store_true",
        help="Actually write to AWS (default is dry run).",
    )
    args = parser.parse_args()

    env     = _load_env()
    payload, missing = _build_payload(env)

    mode = "PUSH" if args.push else "DRY RUN"

    print()
    print("  push_secrets_to_aws.py")
    print(f"  {SEP}")
    print(f"  Mode          : {mode}" + ("" if args.push else "  (pass --push to write)"))
    print(f"  Keys found    : {len(payload)} / {len(SECRETS_TO_PUSH)}")

    if missing:
        missing_str = ", ".join(missing)
        # Wrap at ~38 chars so it fits the panel
        if len(missing_str) > 38:
            parts = []
            line  = ""
            for k in missing:
                if line:
                    candidate = line + ", " + k
                    if len(candidate) > 38:
                        parts.append(line)
                        line = k
                    else:
                        line = candidate
                else:
                    line = k
            if line:
                parts.append(line)
            indent = " " * 18
            missing_display = f"\n{indent}".join(parts)
        else:
            missing_display = missing_str
        print(f"  Keys missing  : {missing_display}")

    print(f"  Would push to : {SECRET_NAME}")
    print(f"                  ({AWS_REGION})")
    print(f"  {SEP}")

    if not args.push:
        print("  Keys that WOULD be pushed (values redacted):")
        for k in sorted(payload):
            print(f"    {k}")
        print()
        print("  Run with --push to write to AWS")
        return

    # ── Live push ──────────────────────────────────────────────────────────
    if not payload:
        print("  ERROR: no keys to push — check your .env file.")
        sys.exit(1)

    print("  Pushing to AWS Secrets Manager...")
    try:
        action = _push_to_aws(payload)
        print(f"  Secret {action} successfully.")
        print()
        print(f"  Keys pushed ({len(payload)}):")
        for k in sorted(payload):
            print(f"    {k}")
        print()
        print(f"  Secret ARN: arn:aws:secretsmanager:{AWS_REGION}:"
              "<account>:secret:{SECRET_NAME}-XXXXXX")
        print()
        print("  Done -- set AWS_SECRETS_NAME=marketpulse-india/prod")
        print("  in your ECS task definition environment.")
    except Exception as exc:
        print(f"  ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
