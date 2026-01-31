BLOCKED_FILENAMES = {".env", ".key", ".pem"}

def evaluate_policy(tool: str, args: dict) -> tuple[bool, str]:
    if tool == "fs.list_dir":
        return True, "Directory listing allowed"

    if tool == "fs.read_file":
        path = args.get("path", "")
        for blocked in BLOCKED_FILENAMES:
            if blocked in path:
                return False, "Access to secret file denied"

        return True, "File read allowed"

    return False, "Unknown tool"