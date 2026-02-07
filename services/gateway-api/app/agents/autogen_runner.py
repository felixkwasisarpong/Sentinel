from __future__ import annotations

import asyncio
import os
from typing import Any

from autogen_agentchat.agents import AssistantAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

try:
    from autogen_core.models import ModelFamily
except Exception:  # pragma: no cover - fallback for older autogen versions
    ModelFamily = None

from .crewai_runner import _parse_gh_task, _parse_gh_english_task, _select_tool
from .crewai_tools import propose_tool_decision

_LAST_TOOL_DECISION: dict | None = None


def _env(name: str, default: str) -> str:
    v = os.getenv(name)
    return v if v else default


def _set_last_tool_decision(td: dict | None) -> None:
    global _LAST_TOOL_DECISION
    _LAST_TOOL_DECISION = td


def _call_tool(tool: str, args: dict, agent_role: str = "autogen") -> str:
    td = propose_tool_decision(tool, args, agent_role)
    _set_last_tool_decision(td)
    if td.get("decision") != "ALLOW":
        return f"[BLOCKED] {td.get('reason')}"
    return td.get("result") or ""


async def call_tool(tool: str, args: dict) -> str:
    """Call any Senteniel-governed tool by name with JSON args."""
    return _call_tool(tool, args, "autogen")


async def fs_list_dir(path: str) -> str:
    """List files in a sandbox directory via Senteniel."""
    return _call_tool("fs.list_dir", {"path": path}, "autogen")


async def fs_read_file(path: str) -> str:
    """Read a sandbox file via Senteniel."""
    return _call_tool("fs.read_file", {"path": path}, "autogen")


async def fs_write_file(path: str, content: str) -> str:
    """Write a sandbox file via Senteniel."""
    return _call_tool("fs.write_file", {"path": path, "content": content}, "autogen")


def _build_model_client() -> OpenAIChatCompletionClient:
    api_base = _env("OPENAI_API_BASE", "")
    if not api_base:
        ollama_base = _env("OLLAMA_BASE_URL", "http://localhost:11434").rstrip("/")
        api_base = f"{ollama_base}/v1"

    model = _env("OPENAI_MODEL_NAME", _env("OLLAMA_MODEL", "llama3.1:8b"))
    api_key = _env("OPENAI_API_KEY", "ollama")

    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "base_url": api_base,
    }

    if ModelFamily:
        family = getattr(ModelFamily, "UNKNOWN", None) or getattr(ModelFamily, "R1", None) or "unknown"
    else:
        family = "unknown"
    model_info = {
        "vision": False,
        "function_calling": True,
        "json_output": False,
        "structured_output": False,
        "family": family,
    }
    kwargs["model_info"] = model_info

    try:
        return OpenAIChatCompletionClient(**kwargs)
    except TypeError:
        # Fallback for older autogen versions that accept model_capabilities.
        kwargs.pop("model_info", None)
        kwargs["model_capabilities"] = {
            "vision": False,
            "function_calling": True,
            "json_output": False,
        }
        return OpenAIChatCompletionClient(**kwargs)


def _final_text_from_result(result: Any) -> str:
    messages = getattr(result, "messages", None)
    if isinstance(messages, list) and messages:
        last = messages[-1]
        content = getattr(last, "content", None)
        if isinstance(content, str):
            return content.strip()
        return str(last).strip()
    return str(result).strip()


async def _run_autogen_async(task: str) -> dict:
    _set_last_tool_decision(None)
    client = _build_model_client()
    agent = AssistantAgent(
        name="autogen",
        model_client=client,
        system_message=(
            "You are a careful agent. Use tools when needed. "
            "For filesystem access, use fs_list_dir/fs_read_file/fs_write_file "
            "and never access paths outside /sandbox. "
            "If a tool returns [BLOCKED], stop and explain that policy blocked the action."
        ),
        tools=[call_tool, fs_list_dir, fs_read_file, fs_write_file],
    )
    try:
        result = await agent.run(task=task)
        return {
            "orchestrator": "autogen",
            "task": task,
            "result": _final_text_from_result(result),
            "tool_decision": _LAST_TOOL_DECISION,
        }
    finally:
        try:
            await client.close()
        except Exception:
            pass


def run_autogen(task: str) -> dict:
    gh = _parse_gh_task(task)
    if gh:
        tool, args = gh
        td = propose_tool_decision(tool, args, "autogen")
        tool_output = td.get("result") if td.get("decision") == "ALLOW" else f"[BLOCKED] {td.get('reason')}"
        return {
            "orchestrator": "autogen",
            "task": task,
            "result": f"Tool Output: {tool_output}\nCompleted.",
            "tool_decision": td,
        }

    gh_tool, gh_args, gh_error = _parse_gh_english_task(task)
    if gh_error:
        tool_decision = {
            "tool_call_id": "n/a",
            "decision": "BLOCK",
            "reason": gh_error,
            "result": None,
            "policy_citations": [],
            "incident_refs": [],
            "control_refs": [],
        }
        return {
            "orchestrator": "autogen",
            "task": task,
            "result": f"Tool Output: [BLOCKED] {gh_error}\nI can't perform that action due to policy restrictions.",
            "tool_decision": tool_decision,
        }
    if gh_tool:
        td = propose_tool_decision(gh_tool, gh_args, "autogen")
        tool_output = td.get("result") if td.get("decision") == "ALLOW" else f"[BLOCKED] {td.get('reason')}"
        return {
            "orchestrator": "autogen",
            "task": task,
            "result": f"Tool Output: {tool_output}\nCompleted.",
            "tool_decision": td,
        }

    forced = _select_tool(task)
    if forced:
        tool, args = forced
        td = propose_tool_decision(tool, args, "autogen")
        tool_output = td.get("result") if td.get("decision") == "ALLOW" else f"[BLOCKED] {td.get('reason')}"
        return {
            "orchestrator": "autogen",
            "task": task,
            "result": f"Tool Output: {tool_output}\nCompleted.",
            "tool_decision": td,
        }

    return asyncio.run(_run_autogen_async(task))
