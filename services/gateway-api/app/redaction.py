SENSITIVE_KEYS = {"password", "secret", "token", "key"}

def redact_args(args: dict) -> dict:
    redacted = {}

    for k, v in args.items():
        if any(s in k.lower() for s in SENSITIVE_KEYS):
            redacted[k] = "***REDACTED***"
        elif isinstance(v, str) and (
            ".env" in v or v.endswith(".key") or v.endswith(".pem")
        ):
            redacted[k] = "***REDACTED_PATH***"
        else:
            redacted[k] = v

    return redacted