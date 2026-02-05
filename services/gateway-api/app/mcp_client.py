import os
import requests

from .db.session import SessionLocal
from .db.queries import get_mcp_server_for_tool

DEFAULT_MCP_URL = os.getenv("MCP_URL", "http://mcp-sandbox:7001")


def _build_tools_endpoint(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/tools"):
        return base
    # Remote MCPs may expose toolsets directly under /mcp/... paths.
    if "/mcp" in base:
        return base
    return f"{base}/tools"


def _build_jsonrpc_endpoint(base_url: str) -> str:
    base = (base_url or "").rstrip("/")
    if base.endswith("/tools"):
        return base[: -len("/tools")]
    return base


def _resolve_mcp_endpoint(tool: str) -> tuple[str, dict]:
    headers = {}
    db = SessionLocal()
    try:
        server = get_mcp_server_for_tool(db, tool)
        if server:
            if server.auth_header and server.auth_token:
                headers[server.auth_header] = server.auth_token
            return _build_tools_endpoint(server.base_url), headers
    finally:
        try:
            db.close()
        except Exception:
            pass

    return _build_tools_endpoint(DEFAULT_MCP_URL), headers


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


def list_tools(base_url: str, auth_header: str | None = None, auth_token: str | None = None) -> list[dict]:
    endpoint = _build_jsonrpc_endpoint(base_url)
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if auth_header and auth_token:
        headers[auth_header] = auth_token

    payload = {
        "jsonrpc": "2.0",
        "id": "tools-list",
        "method": "tools/list",
        "params": {},
    }
    def _post(url: str):
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status()
        return r.json()

    try:
        data = _post(endpoint)
    except requests.HTTPError as exc:
        # Some MCP servers require a trailing slash on the base path (e.g., /mcp/).
        if not endpoint.endswith("/"):
            data = _post(f"{endpoint}/")
        else:
            raise exc

    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            return result["tools"]
        if isinstance(result, list):
            return result

    return []
