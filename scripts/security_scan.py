"""scripts/security_scan.py — manual bandit-equivalent security scanner.

Checks backend/, agents/, mcp_servers/ for the same patterns bandit would flag.
Prints a severity-grouped report and exits 1 if any HIGH issues remain.

Usage:
    python scripts/security_scan.py
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Windows: force UTF-8 so box-drawing characters don't crash on cp1252
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]

ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = ["backend", "agents", "mcp_servers"]

# (bandit_id, label, regex_pattern, severity)
CHECKS: list[tuple[str, str, str, str]] = [
    # ── HIGH: hardcoded secrets ───────────────────────────────────────────────
    ("B105", "hardcoded_password",
     r'password\s*=\s*["\'][^"\']{3,}["\']', "HIGH"),
    ("B106", "hardcoded_password_funcarg",
     r'password=["\'][^"\']{3,}["\']', "HIGH"),
    ("B107", "hardcoded_password_default",
     r'def\s+\w+\(.*password\s*=\s*["\'][^"\']+["\']', "HIGH"),

    # ── HIGH: dangerous deserialization ──────────────────────────────────────
    ("B301", "pickle_loads",
     r'pickle\.loads?\(', "HIGH"),
    ("B302", "marshal_loads",
     r'marshal\.loads?\(', "HIGH"),

    # ── HIGH: unsafe YAML load ────────────────────────────────────────────────
    ("B506", "yaml_load_unsafe",
     r'yaml\.load\s*\([^)]*\)(?!\s*#\s*safe)', "HIGH"),

    # ── HIGH: subprocess with shell=True ─────────────────────────────────────
    ("B602", "subprocess_shell_true",
     r'subprocess\.\w+\s*\([^)]*shell\s*=\s*True', "HIGH"),

    # ── HIGH: SQL injection risk ──────────────────────────────────────────────
    ("B608", "hardcoded_sql_concat",
     r'\.execute\s*\(\s*["\']SELECT[^"\']*["\'\s]*\+', "HIGH"),

    # ── MEDIUM: weak cryptography ─────────────────────────────────────────────
    ("B303", "md5_empty_call",
     r'hashlib\.md5\(\)', "MEDIUM"),
    ("B324", "hashlib_md5_sha1",
     r'hashlib\.(md5|sha1)\(', "MEDIUM"),

    # ── LOW: subprocess without shell ────────────────────────────────────────
    ("B603", "subprocess_no_shell",
     r'subprocess\.(call|run|Popen)\s*\(', "LOW"),
]

_SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
_SEP  = "─" * 60
_THIN = "─" * 60


@dataclass
class Hit:
    bandit_id: str
    label: str
    severity: str
    file: str
    line: int
    text: str
    suppressed: bool = False


def _collect_py_files() -> list[Path]:
    files: list[Path] = []
    for d in SCAN_DIRS:
        for path in (ROOT / d).rglob("*.py"):
            if "__pycache__" not in path.parts:
                files.append(path)
    return sorted(files)


def _is_suppressed(line_text: str, bandit_id: str) -> bool:
    """Return True if the line carries a noqa/nosec suppression for this check."""
    lower = line_text.lower()
    if "nosec" in lower:
        return True
    if f"noqa: {bandit_id.lower()}" in lower or f"noqa: s" in lower:
        return True
    # usedforsecurity=False makes md5/sha1 clearly non-security use
    if bandit_id in ("B303", "B324") and "usedforsecurity=false" in lower:
        return True
    return False


def scan() -> list[Hit]:
    hits: list[Hit] = []
    compiled = [(bid, label, re.compile(pat, re.IGNORECASE), sev)
                for bid, label, pat, sev in CHECKS]

    for pyfile in _collect_py_files():
        try:
            lines = pyfile.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue

        rel = str(pyfile.relative_to(ROOT))
        for lineno, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if stripped.startswith("#"):
                continue
            for bid, label, pattern, sev in compiled:
                if pattern.search(raw):
                    suppressed = _is_suppressed(raw, bid)
                    hits.append(
                        Hit(bid, label, sev, rel, lineno,
                            stripped[:120], suppressed)
                    )
    return hits


def _print_report(hits: list[Hit], total_files: int) -> int:
    active   = [h for h in hits if not h.suppressed]
    by_sev: dict[str, list[Hit]] = {"HIGH": [], "MEDIUM": [], "LOW": []}
    for h in active:
        by_sev[h.severity].append(h)

    suppressed_count = len(hits) - len(active)

    print()
    print("  Manual Security Scan  (bandit-equivalent patterns)")
    print(_SEP)
    print(f"  Files scanned  : {total_files}")
    print(f"  Issues found   : {len(active)}"
          + (f"  ({suppressed_count} suppressed / annotated)" if suppressed_count else ""))
    print(f"    HIGH   (B105,B106,B107,B301,B302,B506,B602,B608): {len(by_sev['HIGH'])}")
    print(f"    MEDIUM (B303,B324):                               {len(by_sev['MEDIUM'])}")
    print(f"    LOW    (B603):                                    {len(by_sev['LOW'])}")
    print(_SEP)

    for sev in ("HIGH", "MEDIUM", "LOW"):
        for h in by_sev[sev]:
            print(f"  [{sev}] {h.bandit_id} {h.label}")
            print(f"        {h.file}:{h.line}")
            print(f"        {h.text}")
            print()

    if suppressed_count:
        print(f"  Suppressed (usedforsecurity=False / noqa / nosec): {suppressed_count}")
        for h in hits:
            if h.suppressed:
                print(f"    {h.file}:{h.line}  [{h.bandit_id}] {h.label}  — annotated")
        print()

    print(_SEP)
    high = len(by_sev["HIGH"])
    if high == 0:
        print("  HIGH severity: 0 ✅")
    else:
        print(f"  HIGH severity: {high}  ❌  Fix before deployment.")
    print()
    return high


def main() -> None:
    files = _collect_py_files()
    hits  = scan()
    high_count = _print_report(hits, len(files))
    sys.exit(1 if high_count > 0 else 0)


if __name__ == "__main__":
    main()
