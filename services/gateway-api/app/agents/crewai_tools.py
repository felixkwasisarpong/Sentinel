import os
import requests
from typing import Type
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

DEFAULT_GQL = "http://localhost:8000/graphql"
GATEWAY_GRAPHQL_URL = os.getenv("GATEWAY_GRAPHQL_URL", DEFAULT_GQL)

PROPOSE_MUTATION = """
mutation Propose($tool: String!, $args: JSON!) {
  proposeToolCall(tool: $tool, args: $args) {
    toolCallId
    decision
    reason
    result
    policyCitations
    incidentRefs
    controlRefs
  }
}
"""

def _normalize_sandbox_path(path: str) -> str | None:
    """
    Enforce that all filesystem paths are under /sandbox.
    - If a relative path is provided, it is treated as relative to /sandbox.
    - If an absolute path outside /sandbox is provided, block it early.
    Returns the normalized absolute path, or None if blocked.
    """
    if not path:
        return "/sandbox"

    p = path.strip()

    # Treat relative paths as under /sandbox
    if not p.startswith("/"):
        p = f"/sandbox/{p}"

    # Collapse accidental double slashes
    while "//" in p:
        p = p.replace("//", "/")

    # Enforce sandbox boundary
    if p == "/sandbox" or p.startswith("/sandbox/"):
        return p

    return None

def _propose_raw(tool: str, args: dict, agent_role: str) -> dict:
    # (Optional) include agent role in args for now; later we’ll store it in DB columns
    args = {**args, "__agent_role": agent_role, "__orchestrator": "crewai"}

    payload = {"query": PROPOSE_MUTATION, "variables": {"tool": tool, "args": args}}
    r = requests.post(GATEWAY_GRAPHQL_URL, json=payload, timeout=10)
    r.raise_for_status()
    return r.json()["data"]["proposeToolCall"]


def _propose(tool: str, args: dict, agent_role: str) -> str:
    data = _propose_raw(tool, args, agent_role)

    if data["decision"] != "ALLOW":
        return f"[BLOCKED] {data['reason']}"

    return data["result"] or ""


def propose_tool_call(tool: str, args: dict, agent_role: str) -> str:
    """
    Public wrapper for deterministic tool execution (bypasses LLM hallucinations).
    """
    # Enforce sandbox boundary for filesystem tools
    if tool in ("fs.list_dir", "fs.read_file", "fs.write_file"):
        norm = _normalize_sandbox_path(str(args.get("path", "")))
        if norm is None:
            return "[BLOCKED] path must be under /sandbox"
        args = {**args, "path": norm}

    return _propose(tool, args, agent_role)


def propose_tool_decision(tool: str, args: dict, agent_role: str) -> dict:
    # Enforce sandbox boundary for filesystem tools
    if tool in ("fs.list_dir", "fs.read_file", "fs.write_file"):
        norm = _normalize_sandbox_path(str(args.get("path", "")))
        if norm is None:
            return {
                "tool_call_id": "n/a",
                "decision": "BLOCK",
                "reason": "path must be under /sandbox",
                "result": None,
                "policy_citations": [],
                "incident_refs": [],
                "control_refs": [],
            }
        args = {**args, "path": norm}

    data = _propose_raw(tool, args, agent_role)
    return {
        "tool_call_id": data.get("toolCallId", "n/a"),
        "decision": data.get("decision"),
        "reason": data.get("reason"),
        "result": data.get("result"),
        "policy_citations": data.get("policyCitations") or [],
        "incident_refs": data.get("incidentRefs") or [],
        "control_refs": data.get("controlRefs") or [],
    }


class ListDirInput(BaseModel):
    path: str = Field(..., description="Directory path to list")


class FSListDirTool(BaseTool):
    name: str = "fs_list_dir"
    description: str = "List files in a sandbox directory (governed by Senteniel policy)."
    args_schema: Type[BaseModel] = ListDirInput

    def __init__(self, agent_role: str):
        super().__init__()
        self._agent_role = agent_role

    def _run(self, path: str) -> str:
        norm = _normalize_sandbox_path(path)
        if norm is None:
            return "[BLOCKED] path must be under /sandbox"
        return _propose("fs.list_dir", {"path": norm}, self._agent_role)


class ReadFileInput(BaseModel):
    path: str = Field(..., description="File path to read")


class FSReadFileTool(BaseTool):
    name: str = "fs_read_file"
    description: str = "Read a file from the sandbox (governed by Senteniel policy)."
    args_schema: Type[BaseModel] = ReadFileInput

    def __init__(self, agent_role: str):
        super().__init__()
        self._agent_role = agent_role

    def _run(self, path: str) -> str:
        norm = _normalize_sandbox_path(path)
        if norm is None:
            return "[BLOCKED] path must be under /sandbox"
        return _propose("fs.read_file", {"path": norm}, self._agent_role)


class WriteFileInput(BaseModel):
    path: str = Field(..., description="File path to write")
    content: str = Field(..., description="Content to write")


class FSWriteFileTool(BaseTool):
    name: str = "fs_write_file"
    description: str = "Write a file in the sandbox (governed by Senteniel policy)."
    args_schema: Type[BaseModel] = WriteFileInput

    def __init__(self, agent_role: str):
        super().__init__()
        self._agent_role = agent_role

    def _run(self, path: str, content: str) -> str:
        norm = _normalize_sandbox_path(path)
        if norm is None:
            return "[BLOCKED] path must be under /sandbox"
        return _propose("fs.write_file", {"path": norm, "content": content}, self._agent_role)
