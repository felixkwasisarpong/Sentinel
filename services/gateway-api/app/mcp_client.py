import os
import requests

from .db.session import SessionLocal
from .db.queries import get_mcp_server_for_tool

DEFAULT_MCP_URL = os.getenv("MCP_URL", "http://mcp-sandbox:7001")


def _resolve_mcp_endpoint(tool: str) -> tuple[str, dict]:
    headers = {}
    db = SessionLocal()
    try:
        server = get_mcp_server_for_tool(db, tool)
        if server:
            if server.auth_header and server.auth_token:
                headers[server.auth_header] = server.auth_token
            return f"{server.base_url.rstrip('/')}/tools", headers
    finally:
        try:
            db.close()
        except Exception:
            pass

    return f"{DEFAULT_MCP_URL.rstrip('/')}/tools", headers


def call_tool(tool: str, args: dict):
    endpoint, headers = _resolve_mcp_endpoint(tool)
    resp = requests.post(
        endpoint,
        json={"tool": tool, "args": args},
        headers=headers,
        timeout=5,
    )
    resp.raise_for_status()
    return resp.json()
