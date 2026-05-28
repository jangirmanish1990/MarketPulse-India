import ast, sys

with open("scripts/smoke_test.py", encoding="utf-8") as f:
    src = f.read()

# AST parse
ast.parse(src)
print("AST parse: OK")

# Check all expected function names
tree = ast.parse(src)
defined = {
    n.name for n in ast.walk(tree)
    if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef))
}
expected = [
    "check_health", "check_auth", "check_trigger_analysis",
    "check_websocket_pipeline", "check_signal_in_db",
    "check_sector_analysis", "run_all", "main",
]
all_ok = True
for name in expected:
    ok = name in defined
    print(f"  {name}: {'OK' if ok else 'MISSING'}")
    if not ok:
        all_ok = False

lines = src.splitlines()
checks = [
    ("Lines", str(len(lines)), True),
    ("Windows ProactorEventLoop", "ProactorEventLoop" in src, True),
    ("UTF-8 reconfigure", "reconfigure" in src, True),
    ("websockets.connect", "websockets.connect" in src, True),
    ("OAuth2 form data (data=)", "data=" in src, True),
    ("SEBI assertion", '"sebi"' in src.lower() or "'sebi'" in src.lower(), True),
    ("--base-url arg", "base-url" in src, True),
    ("WS timeout", "WS_TIMEOUT_S" in src, True),
]
print()
for label, val, _ in checks:
    if isinstance(val, bool):
        print(f"  {label}: {'YES' if val else 'NO'}")
    else:
        print(f"  {label}: {val}")

sys.exit(0 if all_ok else 1)
