"""Pre-launch secrets audit — Task A checks 1-5."""
import re
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parents[1]
SEP = "-" * 50
passed: list[str] = []
failed: list[str] = []


def ok(msg: str) -> None:
    print(f"  ✅ {msg}")
    passed.append(msg)


def fail(msg: str, detail: str = "") -> None:
    print(f"  ❌ {msg}" + (f"  — {detail}" if detail else ""))
    failed.append(msg)


# ── CHECK 1: .env in .gitignore ───────────────────────────────────────────────
gi = (ROOT / ".gitignore").read_text(encoding="utf-8")
if re.search(r"^\.env$", gi, re.MULTILINE) or re.search(r"^\.env\b", gi, re.MULTILINE):
    ok(".env in .gitignore")
else:
    fail(".env in .gitignore", ".env pattern not found")


# ── CHECK 2 & 3: Scan git history for secrets ────────────────────────────────
def _git_log_text() -> str:
    """Return full `git log -p` output as a UTF-8 string, replacing bad bytes."""
    import os
    env = {**os.environ, "GIT_PAGER": "cat", "PAGER": "cat"}
    result = subprocess.run(
        ["git", "--no-pager", "log", "--all", "-p"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=120,
        env=env,
    )
    return result.stdout.decode("utf-8", errors="replace")


try:
    history = _git_log_text()
    count = history.count("sk-ant")
    if count == 0:
        ok("No Anthropic keys in git history")
    else:
        fail("No Anthropic keys in git history", f"{count} match(es) found")
    count2 = len(re.findall(r"AKIA[A-Z2-7]{16}", history))
    if count2 == 0:
        ok("No AWS AKIA keys in git history")
    else:
        fail("No AWS AKIA keys in git history", f"{count2} match(es) found")
except Exception as exc:
    fail("No Anthropic keys in git history", str(exc))
    fail("No AWS AKIA keys in git history", "skipped — git log failed")


# ── CHECK 4: No secrets in working tree code files ───────────────────────────
EXCLUDE_DIRS = {"venv", ".venv", "node_modules", ".git", "cdk.out", "__pycache__"}
CODE_EXTS = {".py", ".ts", ".tsx", ".js", ".json"}
SECRET_PATTERNS = [
    (r"sk-ant-[A-Za-z0-9\-_]{20,}", "Anthropic key"),
    (r"AKIA[A-Z2-7]{16}", "AWS access key"),
    (r"sk-proj-[A-Za-z0-9]{20,}", "OpenAI project key"),
    (r"(?<!['\"])sk-[a-zA-Z0-9]{40,}(?!['\"])", "OpenAI key"),
]
wt_hits: list[str] = []
for fp in ROOT.rglob("*"):
    if any(part in EXCLUDE_DIRS for part in fp.parts):
        continue
    if fp.suffix not in CODE_EXTS or not fp.is_file():
        continue
    try:
        content = fp.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        continue
    for pattern, label in SECRET_PATTERNS:
        if re.search(pattern, content):
            wt_hits.append(f"{fp.relative_to(ROOT)} [{label}]")

if not wt_hits:
    ok("No secrets in working tree (.py/.ts/.tsx/.js/.json)")
else:
    for h in wt_hits:
        fail("Secrets in working tree", h)


# ── CHECK 5: .env.example has no real secret values ──────────────────────────
PLACEHOLDER_RE = re.compile(
    r"replace.me|change.me|your[-_]|localhost|postgresql\+|redis://|"
    r"marketpulse|sk-replace|ARRAY\[|Asia/Kolkata|gpt-4|text-embedding|"
    r"https?://|\.example\.com",
    re.IGNORECASE,
)
example_path = ROOT / ".env.example"
suspicious: list[str] = []
for lineno, line in enumerate(example_path.read_text(encoding="utf-8").splitlines(), 1):
    if not line.strip() or line.strip().startswith("#") or "=" not in line:
        continue
    _, _, val = line.partition("=")
    val = val.split("#")[0].strip()   # strip inline comments
    if not val:
        continue
    if PLACEHOLDER_RE.search(val):
        continue                       # known placeholder pattern — skip
    # Flag values that look like real secrets (long, high-entropy, non-path)
    if len(val) >= 20 and not val.startswith("/") and not val.startswith("."):
        suspicious.append(f"Line {lineno}: {line.strip()[:70]}")

if not suspicious:
    ok(".env.example clean — no real-looking secret values")
else:
    for s in suspicious:
        print(f"    NOTE: {s}")
    fail(".env.example", f"{len(suspicious)} value(s) need review")


# ── SUMMARY ───────────────────────────────────────────────────────────────────
print()
print(f"  {SEP}")
print(f"  Secrets Audit: {len(passed)}/{len(passed)+len(failed)} checks passed")
if not failed:
    print("  All clean — safe to publish ✅")
else:
    for f in failed:
        print(f"  FAIL: {f}")
print(f"  {SEP}")
sys.exit(0 if not failed else 1)
