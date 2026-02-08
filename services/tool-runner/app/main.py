from __future__ import annotations

import json
import os
import select
import shlex
import subprocess
import time
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

_DEFAULT_CMD = "docker mcp gateway run"
_DEFAULT_TIMEOUT = 10.0
_DEFAULT_PROTOCOL_VERSION = "2024-11-05"
_DEFAULT_LIST_MAX_PAGES = 100


class ListToolsRequest(BaseModel):
    command: str | None = None
    timeout: float | None = None
    protocol_version: str | None = None
    max_pages: int | None = None


class CallToolRequest(ListToolsRequest):
    tool_name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ListToolsResponse(BaseModel):
    tools: list[dict[str, Any]]
    count: int


class CallToolResponse(BaseModel):
    result: Any


app = FastAPI(title="Senteniel Tool Runner")


def _normalize_jsonrpc_result(result: Any) -> Any:
    if isinstance(result, dict) and "content" in result:
        content = result.get("content")
        if isinstance(content, list) and content:
            item = content[0]
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if isinstance(text, str) and text.strip().startswith(("{", "[")):
                    try:
                        return json.loads(text)
                    except Exception:
                        pass
                return text
    return result


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


def _terminate_process(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
    except Exception:
        return
    try:
        proc.wait(timeout=1)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _collect_process_output(proc: subprocess.Popen) -> str:
    try:
        stdout_out, stderr_out = proc.communicate(timeout=1)
    except Exception:
        return ""
    return "\n".join(
        [part.strip() for part in (stdout_out or "", stderr_out or "") if part and part.strip()]
    )


def _normalize_process_error(output_text: str) -> str:
    if not output_text:
        return ""
    if "docker: 'mcp' is not a docker command." in output_text:
        return (
            "Docker CLI does not have the MCP plugin in tool-runner. "
            "Install a native Linux docker-mcp plugin in the tool-runner image "
            "or use an MCP_STDIO_CMD available in the container."
        )
    if "Usage:  docker [OPTIONS] COMMAND" in output_text and "Run 'docker COMMAND --help'" in output_text:
        return (
            "Docker CLI does not have the MCP plugin in tool-runner. "
            "Install a native Linux docker-mcp plugin in the tool-runner image "
            "or use an MCP_STDIO_CMD available in the container."
        )
    return output_text


def _read_jsonrpc_response(proc: subprocess.Popen, request_id: Any, timeout: float) -> dict | None:
    if proc.stdout is None:
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        rlist, _, _ = select.select([proc.stdout], [], [], 0.2)
        if not rlist:
            if proc.poll() is not None:
                break
            continue
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                break
            continue
        line = line.strip()
        if not line:
            continue
        if line.startswith("data:"):
            line = line[len("data:"):].strip()
        try:
            data = json.loads(line)
        except Exception:
            continue
        if isinstance(data, dict) and data.get("id") == request_id:
            return data
    return None


def _write_payload(proc: subprocess.Popen, payload: dict) -> None:
    if proc.stdin is None:
        raise RuntimeError("MCP stdio stdin unavailable")
    proc.stdin.write(json.dumps(payload) + "\n")
    proc.stdin.flush()


def _resolve_command(command: str | None) -> str:
    return command or os.getenv("MCP_STDIO_CMD") or _DEFAULT_CMD


def _resolve_timeout(timeout: float | None) -> float:
    if timeout is not None:
        return float(timeout)
    return float(os.getenv("MCP_STDIO_TIMEOUT", _DEFAULT_TIMEOUT))


def _resolve_protocol_version(protocol_version: str | None) -> str:
    return protocol_version or os.getenv("MCP_STDIO_PROTOCOL_VERSION", _DEFAULT_PROTOCOL_VERSION)


def _start_process(command: str, timeout: float, protocol_version: str) -> subprocess.Popen:
    cmd = shlex.split(command)
    if not cmd:
        raise RuntimeError("MCP stdio command is empty")
    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        program = cmd[0]
        raise RuntimeError(
            f"MCP stdio gateway command not found: {program}. "
            "Ensure Docker CLI is installed where tool-runner runs."
        ) from exc

    init_id = "initialize"
    init_payload = {
        "jsonrpc": "2.0",
        "id": init_id,
        "method": "initialize",
        "params": {
            "protocolVersion": protocol_version,
            "capabilities": {},
            "clientInfo": {"name": "senteniel-tool-runner", "version": "0.1.0"},
        },
    }
    _write_payload(proc, init_payload)
    init_data = _read_jsonrpc_response(proc, init_id, timeout)
    if init_data is None:
        _terminate_process(proc)
        output_text = _normalize_process_error(_collect_process_output(proc))
        if output_text:
            raise RuntimeError(output_text)
        raise RuntimeError("No response to MCP initialize request")
    init_err = _jsonrpc_error_message(init_data)
    if init_err:
        _terminate_process(proc)
        raise RuntimeError(f"MCP initialize error: {init_err}")

    initialized_notification = {
        "jsonrpc": "2.0",
        "method": "notifications/initialized",
        "params": {},
    }
    _write_payload(proc, initialized_notification)
    return proc


def _request_with_proc(proc: subprocess.Popen, payload: dict, timeout: float) -> dict:
    _write_payload(proc, payload)
    data = _read_jsonrpc_response(proc, payload.get("id", ""), timeout)
    if data is not None:
        return data

    _terminate_process(proc)
    output_text = _normalize_process_error(_collect_process_output(proc))
    if output_text:
        raise RuntimeError(f"MCP stdio gateway error: {output_text}")
    raise RuntimeError("No response from MCP stdio gateway")


def _request_once(payload: dict, *, command: str, timeout: float, protocol_version: str) -> dict:
    proc = _start_process(command, timeout, protocol_version)
    try:
        return _request_with_proc(proc, payload, timeout)
    finally:
        _terminate_process(proc)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/v1/mcp/list-tools", response_model=ListToolsResponse)
def list_tools(request: ListToolsRequest) -> ListToolsResponse:
    command = _resolve_command(request.command)
    timeout = _resolve_timeout(request.timeout)
    protocol_version = _resolve_protocol_version(request.protocol_version)
    max_pages = int(request.max_pages or os.getenv("MCP_STDIO_LIST_MAX_PAGES", _DEFAULT_LIST_MAX_PAGES))
    if max_pages <= 0:
        max_pages = _DEFAULT_LIST_MAX_PAGES

    tools: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    cursor = None

    try:
        proc = _start_process(command, timeout, protocol_version)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        for i in range(max_pages):
            params = {"cursor": cursor} if cursor else {}
            payload = {
                "jsonrpc": "2.0",
                "id": f"tools-list-{i}",
                "method": "tools/list",
                "params": params,
            }
            try:
                data = _request_with_proc(proc, payload, timeout)
            except RuntimeError as exc:
                raise HTTPException(status_code=502, detail=str(exc))

            err = _jsonrpc_error_message(data)
            if err:
                raise HTTPException(status_code=502, detail=f"MCP error: {err}")
            result = data.get("result")

            batch: list[dict[str, Any]] = []
            next_cursor = None
            if isinstance(result, dict):
                if isinstance(result.get("tools"), list):
                    batch = [t for t in result["tools"] if isinstance(t, dict)]
                next_cursor = result.get("nextCursor") or result.get("next_cursor") or result.get("cursor")
            elif isinstance(result, list):
                batch = [t for t in result if isinstance(t, dict)]

            for tool in batch:
                name = tool.get("name")
                key = str(name) if name is not None else json.dumps(tool, sort_keys=True)
                if key in seen_names:
                    continue
                seen_names.add(key)
                tools.append(tool)

            if not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
    finally:
        _terminate_process(proc)

    return ListToolsResponse(tools=tools, count=len(tools))


@app.post("/v1/mcp/call-tool", response_model=CallToolResponse)
def call_tool(request: CallToolRequest) -> CallToolResponse:
    command = _resolve_command(request.command)
    timeout = _resolve_timeout(request.timeout)
    protocol_version = _resolve_protocol_version(request.protocol_version)
    payload = {
        "jsonrpc": "2.0",
        "id": "tools-call",
        "method": "tools/call",
        "params": {"name": request.tool_name, "arguments": request.args or {}},
    }

    try:
        data = _request_once(
            payload,
            command=command,
            timeout=timeout,
            protocol_version=protocol_version,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    err = _jsonrpc_error_message(data)
    if err:
        raise HTTPException(status_code=502, detail=f"MCP error: {err}")
    result = _normalize_jsonrpc_result(data.get("result"))
    return CallToolResponse(result=result)
