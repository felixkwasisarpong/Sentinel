import os
import json
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


def _uses_jsonrpc(base_url: str) -> bool:
    return "/mcp" in (base_url or "")


def _resolve_mcp_endpoint(tool: str) -> tuple[str, dict, str | None, bool]:
    headers = {}
    db = SessionLocal()
    try:
        server = get_mcp_server_for_tool(db, tool)
        if server:
            if server.auth_header and server.auth_token:
                headers[server.auth_header] = server.auth_token
            return server.base_url, headers, server.tool_prefix, _uses_jsonrpc(server.base_url)
    finally:
        try:
            db.close()
        except Exception:
            pass

    return DEFAULT_MCP_URL, headers, None, _uses_jsonrpc(DEFAULT_MCP_URL)


def _parse_jsonrpc_response(resp: requests.Response) -> dict:
    content_type = (resp.headers.get("Content-Type") or "").lower()
    text = resp.text or ""
    if "text/event-stream" in content_type or text.strip().startswith("data:"):
        data_lines = []
        for line in text.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if data_lines:
            return json.loads(data_lines[-1])
    if not text.strip():
        raise ValueError("Empty response from MCP endpoint")
    try:
        return resp.json()
    except json.JSONDecodeError:
        data_lines = []
        for line in text.splitlines():
            if line.startswith("data:"):
                data_lines.append(line[len("data:"):].strip())
        if data_lines:
            return json.loads(data_lines[-1])
        raise


def _jsonrpc_error_message(data: dict) -> str | None:
    if not isinstance(data, dict):
        return None
    err = data.get("error")
    if not err:
        return None
    if isinstance(err, dict):
        msg = err.get("message") or err.get("error") or "Unknown MCP error"
        details = err.get("data")
        if details:
            return f"{msg} ({details})"
        return msg
    return str(err)


def call_tool(tool: str, args: dict):
    base_url, headers, prefix, jsonrpc = _resolve_mcp_endpoint(tool)
    tool_name = tool
    if prefix and tool_name.startswith(prefix):
        tool_name = tool_name[len(prefix):]
    if jsonrpc:
        endpoint = _build_jsonrpc_endpoint(base_url)
        payload = {
            "jsonrpc": "2.0",
            "id": "tools-call",
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": args},
        }
        resp = requests.post(
            endpoint,
            json=payload,
            headers={**headers, "Content-Type": "application/json", "Accept": "application/json, text/event-stream"},
            timeout=10,
        )
        resp.raise_for_status()
        data = _parse_jsonrpc_response(resp)
        err = _jsonrpc_error_message(data)
        if err:
            raise requests.RequestException(f"MCP error: {err}")
        result = data.get("result")
        # Normalize to match MCP /tools shape
        if isinstance(result, dict) and "content" in result:
            content = result.get("content")
            if isinstance(content, list) and content:
                item = content[0]
                if isinstance(item, dict) and item.get("type") == "text":
                    text = item.get("text", "")
                    if isinstance(text, str) and text.strip().startswith(("{", "[")):
                        try:
                            return {"result": json.loads(text)}
                        except Exception:
                            pass
                    return {"result": text}
        return {"result": result}

    endpoint = _build_tools_endpoint(base_url)
    resp = requests.post(
        endpoint,
        json={"tool": tool_name, "args": args},
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
        return _parse_jsonrpc_response(r)

    try:
        data = _post(endpoint)
    except requests.HTTPError as exc:
        # Some MCP servers require a trailing slash on the base path (e.g., /mcp/).
        if not endpoint.endswith("/"):
            data = _post(f"{endpoint}/")
        else:
            raise exc
    err = _jsonrpc_error_message(data)
    if err:
        raise requests.RequestException(f"MCP error: {err}")

    if isinstance(data, dict):
        result = data.get("result")
        if isinstance(result, dict) and isinstance(result.get("tools"), list):
            return result["tools"]
        if isinstance(result, list):
            return result

    return []
