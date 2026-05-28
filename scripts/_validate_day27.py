"""Day 27 local validation — CHECK 2 (manifest) + CHECK 4 (CDK) + CHECK 5 (YAML)."""
import glob
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

all_passed = True

# ── CHECK 2 — manifest.json ──────────────────────────────────────────────────
print("=== CHECK 2 — PWA manifest ===")
try:
    with open("frontend/public/manifest.json") as f:
        m = json.load(f)
    checks = [
        ("name",             m.get("name")             == "MarketPulse India"),
        ("theme_color",      m.get("theme_color")      == "#FF9500"),
        ("background_color", m.get("background_color") == "#04080F"),
        ("icons count",      len(m.get("icons", []))   == 2),
        ("shortcuts count",  len(m.get("shortcuts", [])) == 2),
        ("display",          m.get("display")          == "standalone"),
        ("start_url",        m.get("start_url")        == "/"),
    ]
    for label, result in checks:
        icon = "OK" if result else "FAIL"
        print(f"  {label:<20}: {icon}")
        if not result:
            all_passed = False
    print("  manifest.json valid")
except Exception as exc:
    print(f"  ERROR: {exc}")
    all_passed = False

print()

# ── CHECK 4 — CDK synth ──────────────────────────────────────────────────────
print("=== CHECK 4 — CDK synth ===")
env = {**os.environ, "CDK_DEFAULT_ACCOUNT": "775935274215", "CDK_DEFAULT_REGION": "ap-south-1"}
result = subprocess.run(
    ["cdk", "synth", "--app", "python infra/app.py"],
    capture_output=True, text=True, env=env,
)
if result.returncode == 0:
    templates = sorted(glob.glob("cdk.out/*.template.json"))
    for t in templates:
        kb = round(os.path.getsize(t) / 1024, 1)
        name = os.path.basename(t).replace(".template.json", "")
        marker = " <-- new" if "Frontend" in name else ""
        print(f"  {name:<42} {kb:>6.1f} KB{marker}")
    if not any("FrontendStack" in t for t in templates):
        print("  MarketPulseFrontendStack NOT FOUND")
        all_passed = False
    else:
        print("  MarketPulseFrontendStack present")
else:
    print(f"  CDK synth FAILED:\n{result.stderr[-500:]}")
    all_passed = False

print()

# ── CHECK 5 — GitHub Actions YAML ────────────────────────────────────────────
print("=== CHECK 5 — GitHub Actions YAML ===")
try:
    import yaml
    workflows = sorted(glob.glob(".github/workflows/*.yml"))
    for wf in workflows:
        with open(wf) as fh:
            doc = yaml.safe_load(fh)
        jobs = list(doc.get("jobs", {}).keys())
        print(f"  {os.path.basename(wf):<30} jobs={jobs}")
    print("  All YAML files valid")
except Exception as exc:
    print(f"  ERROR: {exc}")
    all_passed = False

print()
sys.exit(0 if all_passed else 1)
