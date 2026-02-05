import json
import os
from functools import lru_cache

BLOCKED_FILENAMES = {".env", ".key", ".pem"}


def _is_under_sandbox(path: str) -> bool:
    return path == "/sandbox" or path.startswith("/sandbox/")


@lru_cache(maxsize=1)
def _prefix_rules() -> list[tuple[str, dict]]:
    raw = os.getenv("POLICY_PREFIX_RULES", "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []

    rules: list[tuple[str, dict]] = []
    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(k, str) and isinstance(v, dict):
                rules.append((k, v))
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and isinstance(item.get("prefix"), str):
                rules.append((item["prefix"], item))

    rules.sort(key=lambda r: len(r[0]), reverse=True)
    return rules


def _policy_from_prefix(tool: str) -> tuple[str, str, float] | None:
    for prefix, rule in _prefix_rules():
        if tool.startswith(prefix):
            decision = str(rule.get("decision", "BLOCK")).upper()
            reason = rule.get("reason") or "Policy prefix match"
            try:
                risk = float(rule.get("risk", 0.5))
            except Exception:
                risk = 0.5
            if decision not in ("ALLOW", "BLOCK", "APPROVAL_REQUIRED"):
                decision = "BLOCK"
            return decision, reason, risk
    return None


def evaluate_policy(tool: str, args: dict) -> tuple[str, str, float]:
    if tool == "fs.list_dir":
        path = str(args.get("path", "") or "/sandbox")
        if not _is_under_sandbox(path):
            return "BLOCK", "path must be under /sandbox", 1.0
        return "ALLOW", "Directory listing allowed", 0.0

    if tool == "fs.read_file":
        path = str(args.get("path", ""))
        if path and not _is_under_sandbox(path):
            return "BLOCK", "path must be under /sandbox", 1.0
        for blocked in BLOCKED_FILENAMES:
            if blocked in path:
                return "BLOCK", "Access to secret file denied", 1.0

        return "ALLOW", "File read allowed", 0.0

    if tool == "fs.write_file":
        path = str(args.get("path", ""))
        if path and not path.startswith("/"):
            path = f"/sandbox/{path.lstrip('/')}"
        if not _is_under_sandbox(path):
            return "BLOCK", "path must be under /sandbox", 1.0
        return "APPROVAL_REQUIRED", "Write requires approval", 0.7

    prefix_policy = _policy_from_prefix(tool)
    if prefix_policy is not None:
        return prefix_policy

    return "BLOCK", "Unknown tool", 1.0
