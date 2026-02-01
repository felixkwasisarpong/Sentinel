from pathlib import Path

SANDBOX_ROOT = Path("/sandbox").resolve()
SANDBOX_ROOT.mkdir(parents=True, exist_ok=True)

def validate_path(path: str) -> Path:
    sandbox_root_str = str(SANDBOX_ROOT)
    if path.startswith("/"):
        if path == sandbox_root_str or path.startswith(sandbox_root_str + "/"):
            rel = path[len(sandbox_root_str):].lstrip("/")
            candidate = (SANDBOX_ROOT / rel).resolve()
        else:
            raise ValueError("path must be under /sandbox")
    else:
        candidate = (SANDBOX_ROOT / path).resolve()

    if not str(candidate).startswith(sandbox_root_str):
        raise ValueError("path must be under /sandbox")

    return candidate

def is_secret(path: Path) -> bool:
    return path.name.startswith(".") or path.suffix in {".env", ".key", ".pem"}
