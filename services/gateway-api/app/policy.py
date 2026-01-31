BLOCKED_FILENAMES = {".env", ".key", ".pem"}

def evaluate_policy(tool: str, args: dict) -> tuple[bool, str, float]:
    if tool == "fs.list_dir":
        return True, "Directory listing allowed", 0.0

    if tool == "fs.read_file":
        path = args.get("path", "")
        for blocked in BLOCKED_FILENAMES:
            if blocked in path:
                return False, "Access to secret file denied", 1.0

        return True, "File read allowed", 0.0

    return False, "Unknown tool", 1.0
