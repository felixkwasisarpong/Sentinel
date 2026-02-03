BLOCKED_FILENAMES = {".env", ".key", ".pem"}


def _is_under_sandbox(path: str) -> bool:
    return path == "/sandbox" or path.startswith("/sandbox/")


def evaluate_policy(tool: str, args: dict) -> tuple[str, str, float]:
    if tool == "fs.list_dir":
        return "ALLOW", "Directory listing allowed", 0.0

    if tool == "fs.read_file":
        path = str(args.get("path", ""))
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

    return "BLOCK", "Unknown tool", 1.0
