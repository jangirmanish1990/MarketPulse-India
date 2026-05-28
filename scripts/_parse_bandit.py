"""Parse bandit_report.json and print a concise summary."""
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

with open("tests/security/bandit_report.json") as f:
    r = json.load(f)

results = r.get("results", [])
metrics = r.get("metrics", {})
all_files = [k for k in metrics if k != "_totals"]

by_sev: dict[str, list] = {"HIGH": [], "MEDIUM": [], "LOW": []}
for issue in results:
    sev = issue.get("issue_severity", "LOW")
    if sev in by_sev:
        by_sev[sev].append(issue)

SEP = "-" * 42
print()
print("  Bandit Security Scan")
print(f"  {SEP}")
print(f"  Files scanned    : {len(all_files)}")
print(f"  HIGH severity    : {len(by_sev['HIGH'])}")
print(f"  MEDIUM severity  : {len(by_sev['MEDIUM'])}")
print(f"  LOW severity     : {len(by_sev['LOW'])}")
print(f"  {SEP}")

def short(path: str) -> str:
    return path.replace("\\", "/").split("MarketPulse-India/")[-1]

for sev in ("HIGH", "MEDIUM"):
    if by_sev[sev]:
        print(f"\n  {sev} issues:")
        for i in by_sev[sev]:
            print(f"    {short(i['filename'])}:{i['line_number']}"
                  f"  [{i['test_id']}]  {i['issue_text'][:90]}")

if not by_sev["HIGH"]:
    print("\n  Bandit scan complete - 0 HIGH")
else:
    print(f"\n  {len(by_sev['HIGH'])} HIGH issue(s) must be fixed before proceeding.")

sys.exit(1 if by_sev["HIGH"] else 0)
