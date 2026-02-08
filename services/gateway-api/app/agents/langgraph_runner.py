import os
import re
import json
import shlex
import requests

from langgraph.graph import StateGraph, END
from langchain_core.messages import SystemMessage, HumanMessage

from .state import AgentState
from .prompts import PLANNER_PROMPT, INTERPRETER_PROMPT
from app.llm import get_langchain_chat_llm


# Use env override so this works both inside Docker and on host.
GATEWAY_GRAPHQL_URL = os.getenv("GATEWAY_GRAPHQL_URL", "http://localhost:8000/graphql")
GITHUB_DEFAULT_OWNER = os.getenv("GITHUB_OWNER") or os.getenv("GH_OWNER")
GITHUB_DEFAULT_REPO = os.getenv("GITHUB_REPO") or os.getenv("GH_REPO")

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


def _llm_text(system: str, user: str) -> str:
    """
    Call the local chat model (Ollama via langchain-ollama) and return plain text.
    """
    llm = get_langchain_chat_llm()
    try:
        resp = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
        return getattr(resp, "content", str(resp)).strip()
    except Exception:
        # If Ollama/LLM is unavailable (e.g., connection refused), fall back to deterministic logic.
        return ""


def _extract_path(text: str) -> str | None:
    """
    Extract an absolute path from free-form text, stopping at whitespace/quotes.
    """
    if not text:
        return None
    m = re.search(r'(/[^\s"\']+)', text)
    return m.group(1) if m else None


def _parse_kv_args(tokens: list[str]) -> dict:
    args: dict = {}
    for token in tokens:
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        v = value.strip()
        if v.lower() in ("true", "false"):
            args[key] = v.lower() == "true"
            continue
        # int / float coercion
        try:
            if "." in v:
                args[key] = float(v)
            else:
                args[key] = int(v)
            continue
        except Exception:
            pass
        # JSON object/array
        if (v.startswith("{") and v.endswith("}")) or (v.startswith("[") and v.endswith("]")):
            try:
                args[key] = json.loads(v)
                continue
            except Exception:
                pass
        args[key] = v
    return args


def _looks_like_explicit_tool_name(name: str) -> bool:
    if not name or "." not in name:
        return False
    if name.startswith(".") or name.endswith("."):
        return False
    return True


def _parse_explicit_tool_task(task: str) -> tuple[str, dict] | None:
    t = (task or "").strip()
    if not t:
        return None
    head = t.split(None, 1)
    tool = head[0]
    if not _looks_like_explicit_tool_name(tool):
        return None
    if len(head) == 1:
        return tool, {}
    rest_raw = head[1].strip()
    if rest_raw.startswith("{") and rest_raw.endswith("}"):
        try:
            parsed = json.loads(rest_raw)
            if isinstance(parsed, dict):
                return tool, parsed
        except Exception:
            pass
    try:
        parts = shlex.split(t)
    except Exception:
        return None
    if not parts:
        return None
    if len(parts) == 1:
        return tool, {}
    return tool, _parse_kv_args(parts[1:])


def _parse_gh_task(task: str) -> tuple[str, dict] | None:
    t = (task or "").strip()
    if not t.startswith("gh."):
        return None
    parts = shlex.split(t)
    if not parts:
        return None
    tool = parts[0]
    if len(parts) == 1:
        return tool, {}
    rest = " ".join(parts[1:]).strip()
    if rest.startswith("{") and rest.endswith("}"):
        try:
            return tool, json.loads(rest)
        except Exception:
            return tool, {}
    return tool, _parse_kv_args(parts[1:])


def _extract_gh_owner_repo(text: str) -> tuple[str | None, str | None]:
    if not text:
        return None, None
    m = re.search(r'(?:repo|repository|in)\s+([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)', text, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r'owner\s+([A-Za-z0-9_.-]+)\s+repo\s+([A-Za-z0-9_.-]+)', text, re.IGNORECASE)
    if m:
        return m.group(1), m.group(2)
    m = re.search(r'repo\s+([A-Za-z0-9_.-]+)', text, re.IGNORECASE)
    if m:
        return None, m.group(1)
    # Issues in <repo>
    m = re.search(r'issues?\s+in\s+([A-Za-z0-9_.-]+)', text, re.IGNORECASE)
    if m:
        return None, m.group(1)
    m = re.search(r'issue\s*#?\d+\s+in\s+([A-Za-z0-9_.-]+)', text, re.IGNORECASE)
    if m:
        return None, m.group(1)
    return None, None


def _extract_gh_issue_number(text: str) -> int | None:
    if not text:
        return None
    m = re.search(r'issue\s*#?(\d+)', text, re.IGNORECASE)
    if not m:
        return None
    try:
        return int(m.group(1))
    except Exception:
        return None


def _extract_quoted_text(text: str) -> str | None:
    if not text:
        return None
    matches = re.findall(r'["\']([^"\']+)["\']', text)
    if matches:
        return matches[-1].strip()
    return None


def _extract_comment_body(text: str) -> str | None:
    if not text:
        return None
    quoted = _extract_quoted_text(text)
    if quoted:
        return quoted
    m = re.search(r'comment\s*:\s*(.+)$', text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r'comment\s+(.+?)\s+(?:on|to)\s+issue', text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"\'')
    return None


def _extract_search_term(text: str) -> str | None:
    if not text:
        return None
    quoted = _extract_quoted_text(text)
    if quoted:
        return quoted
    m = re.search(r'for\s+(.+)$', text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"\'')
    m = re.search(r'about\s+(.+)$', text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"\'')
    return None


def _parse_gh_english_task(task: str) -> tuple[str | None, dict, str | None]:
    if not task:
        return None, {}, None
    t = task.strip()
    t_l = t.lower()
    # Only engage if it looks GitHub-related
    if not any(word in t_l for word in ("issue", "issues", "repo", "repository", "github", "comment", "search")):
        return None, {}, None

    owner, repo = _extract_gh_owner_repo(t)
    if not owner:
        owner = GITHUB_DEFAULT_OWNER
    if not repo:
        repo = GITHUB_DEFAULT_REPO

    issue_number = _extract_gh_issue_number(t)

    if "comment" in t_l and issue_number:
        if not owner or not repo:
            return None, {}, "Missing repo. Add 'owner/REPO' or set GITHUB_OWNER/GITHUB_REPO."
        body = _extract_comment_body(t)
        if not body:
            return None, {}, "Missing comment text. Add it in quotes, e.g. comment \"LGTM\"."
        return "gh.add_issue_comment", {
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number,
            "body": body,
        }, None

    if "comments" in t_l and issue_number:
        if not owner or not repo:
            return None, {}, "Missing repo. Add 'owner/REPO' or set GITHUB_OWNER/GITHUB_REPO."
        return "gh.list_issue_comments", {
            "owner": owner,
            "repo": repo,
            "issue_number": issue_number,
        }, None

    if "list" in t_l and "issues" in t_l:
        if not owner or not repo:
            return None, {}, "Missing repo. Add 'owner/REPO' or set GITHUB_OWNER/GITHUB_REPO."
        return "gh.list_issues", {"owner": owner, "repo": repo}, None

    if issue_number and any(word in t_l for word in ("show", "read", "details", "get")):
        if not owner or not repo:
            return None, {}, "Missing repo. Add 'owner/REPO' or set GITHUB_OWNER/GITHUB_REPO."
        return "gh.issue_read", {"owner": owner, "repo": repo, "issue_number": issue_number}, None

    if "search" in t_l and "issues" in t_l:
        term = _extract_search_term(t)
        if not term and not (owner and repo):
            return None, {}, "Missing search term and repo. Add 'for <term>' and repo."
        if owner and repo:
            query = f"repo:{owner}/{repo} {term or 'is:issue'}".strip()
        else:
            query = term or ""
        return "gh.search_issues", {"query": query}, None

    return None, {}, None


def _extract_write_content(text: str) -> str:
    if not text:
        return ""
    m = re.search(r'write\s+(.+?)\s+to\s+(/[^\s"\']+)', text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"\'')
    m = re.search(r'write\s+(.+?)\s+into\s+(/[^\s"\']+)', text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"\'')
    m = re.search(r'write\s+(.+)$', text, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"\'')
    return ""


def _normalize_sandbox_path(path: str | None) -> str | None:
    """
    Enforce that all filesystem paths are under /sandbox.
    - Relative paths become /sandbox/<path>
    - Absolute paths outside /sandbox are blocked.
    Returns normalized absolute path, or None if blocked.
    """
    if not path:
        return "/sandbox"

    p = path.strip()

    if not p.startswith("/"):
        p = f"/sandbox/{p}"

    while "//" in p:
        p = p.replace("//", "/")

    if p == "/sandbox" or p.startswith("/sandbox/"):
        return p

    return None


def planner_node(state: AgentState) -> AgentState:
    """
    Produce a plan that explicitly names the intended tool: fs.list_dir, fs.read_file, or fs.write_file.

    IMPORTANT: Planning does not execute tools.
    """
    task = state["user_task"]

    system = "You are a careful planner for a tool-using agent. Never execute tools; only plan."
    user = PLANNER_PROMPT.format(task=task) + (
        "\n\nConstraints:\n"
        "- If tools are needed, the plan MUST mention exactly one of: fs.list_dir, fs.read_file, or fs.write_file.\n"
        "- If a filesystem path is relevant, include it in the plan.\n"
        "- If no tool is needed, say: No tool required.\n"
        "- Keep the plan short (1-3 sentences).\n"
    )

    plan = _llm_text(system, user)

    if not plan:
        plan = ""

    # Safety fallback: if model output doesn't include a tool name and isn't 'No tool required', fall back to heuristics.
    plan_l = plan.lower()
    if ("fs.list_dir" not in plan_l) and ("fs.read_file" not in plan_l) and ("fs.write_file" not in plan_l) and ("no tool required" not in plan_l):
        t_l = task.lower()
        if "list" in t_l:
            plan = "Use fs.list_dir to inspect /sandbox"
        elif "read" in t_l:
            p = _extract_path(task) or "/sandbox/example.txt"
            plan = f"Use fs.read_file to read {p}"
        elif "write" in t_l:
            p = _extract_path(task) or "/sandbox/hello.txt"
            plan = f"Use fs.write_file to write to {p}"
        else:
            plan = "No tool required"

    return {**state, "plan": plan}


def tool_proposer_node(state: AgentState) -> AgentState:
    """
    Deterministic tool proposal: chooses args based on the plan text and the original task,
    and calls Senteniel's GraphQL control plane (NOT MCP directly).
    """
    task = state["user_task"]
    plan = state.get("plan") or ""
    plan_l = plan.lower()

    tool: str | None = None
    args: dict | None = None

    explicit = _parse_explicit_tool_task(task)
    if explicit:
        tool, args = explicit
        args = {**args, "__orchestrator": "langgraph", "__agent_role": "single"}
        payload = {
            "query": PROPOSE_MUTATION,
            "variables": {"tool": tool, "args": args},
        }
        try:
            resp = requests.post(GATEWAY_GRAPHQL_URL, json=payload, timeout=10)
            resp.raise_for_status()
            body = resp.json()
            data = body["data"]["proposeToolCall"]
        except Exception as e:
            tool_decision = {
                "tool_call_id": "n/a",
                "decision": "BLOCK",
                "reason": f"gateway request failed: {e}",
                "result": None,
                "policy_citations": [],
                "incident_refs": [],
                "control_refs": [],
            }
            return {**state, "tool_result": f"[ERROR] gateway request failed: {e}", "tool_decision": tool_decision}

        tool_decision = {
            "tool_call_id": data.get("toolCallId", "n/a"),
            "decision": data.get("decision"),
            "reason": data.get("reason"),
            "result": data.get("result"),
            "policy_citations": data.get("policyCitations") or [],
            "incident_refs": data.get("incidentRefs") or [],
            "control_refs": data.get("controlRefs") or [],
        }

        if data["decision"] != "ALLOW":
            return {**state, "tool_result": f"[BLOCKED] {data['reason']}", "tool_decision": tool_decision}

        return {**state, "tool_result": data.get("result"), "tool_decision": tool_decision}

    # GitHub MCP direct tool invocation, e.g.:
    #   gh.add_issue_comment owner=... repo=... issue_number=1 body="test"
    gh = _parse_gh_task(task)
    if gh:
        tool, args = gh
        args = {**args, "__orchestrator": "langgraph", "__agent_role": "single"}
        payload = {
            "query": PROPOSE_MUTATION,
            "variables": {"tool": tool, "args": args},
        }
        try:
            resp = requests.post(GATEWAY_GRAPHQL_URL, json=payload, timeout=10)
            resp.raise_for_status()
            body = resp.json()
            data = body["data"]["proposeToolCall"]
        except Exception as e:
            tool_decision = {
                "tool_call_id": "n/a",
                "decision": "BLOCK",
                "reason": f"gateway request failed: {e}",
                "result": None,
                "policy_citations": [],
                "incident_refs": [],
                "control_refs": [],
            }
            return {**state, "tool_result": f"[ERROR] gateway request failed: {e}", "tool_decision": tool_decision}

        tool_decision = {
            "tool_call_id": data.get("toolCallId", "n/a"),
            "decision": data.get("decision"),
            "reason": data.get("reason"),
            "result": data.get("result"),
            "policy_citations": data.get("policyCitations") or [],
            "incident_refs": data.get("incidentRefs") or [],
            "control_refs": data.get("controlRefs") or [],
        }

        if data["decision"] != "ALLOW":
            return {**state, "tool_result": f"[BLOCKED] {data['reason']}", "tool_decision": tool_decision}

        return {**state, "tool_result": data.get("result"), "tool_decision": tool_decision}

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
        return {**state, "tool_result": f"[BLOCKED] {gh_error}", "tool_decision": tool_decision}
    if gh_tool:
        tool = gh_tool
        args = {**gh_args, "__orchestrator": "langgraph", "__agent_role": "single"}
        payload = {
            "query": PROPOSE_MUTATION,
            "variables": {"tool": tool, "args": args},
        }
        try:
            resp = requests.post(GATEWAY_GRAPHQL_URL, json=payload, timeout=10)
            resp.raise_for_status()
            body = resp.json()
            data = body["data"]["proposeToolCall"]
        except Exception as e:
            tool_decision = {
                "tool_call_id": "n/a",
                "decision": "BLOCK",
                "reason": f"gateway request failed: {e}",
                "result": None,
                "policy_citations": [],
                "incident_refs": [],
                "control_refs": [],
            }
            return {**state, "tool_result": f"[ERROR] gateway request failed: {e}", "tool_decision": tool_decision}

        tool_decision = {
            "tool_call_id": data.get("toolCallId", "n/a"),
            "decision": data.get("decision"),
            "reason": data.get("reason"),
            "result": data.get("result"),
            "policy_citations": data.get("policyCitations") or [],
            "incident_refs": data.get("incidentRefs") or [],
            "control_refs": data.get("controlRefs") or [],
        }

        if data["decision"] != "ALLOW":
            return {**state, "tool_result": f"[BLOCKED] {data['reason']}", "tool_decision": tool_decision}

        return {**state, "tool_result": data.get("result"), "tool_decision": tool_decision}

    # Prefer plan tool selection, fall back to task keywords.
    if "fs.list_dir" in plan_l or ("list" in task.lower() and "file" in task.lower()):
        tool = "fs.list_dir"
        task_path = _extract_path(task)
        plan_path = _extract_path(plan)
        raw_path = task_path or plan_path or "/sandbox"
        if task_path is not None:
            norm = _normalize_sandbox_path(task_path)
            args = {"path": task_path if norm is None else norm}
        else:
            norm = _normalize_sandbox_path(raw_path)
            args = {"path": raw_path if norm is None else norm}
    elif "fs.read_file" in plan_l or "read" in task.lower():
        tool = "fs.read_file"
        # Prefer an explicit path from the user's original task; only fall back to plan/default if none was provided.
        task_path = _extract_path(task)
        plan_path = _extract_path(plan)
        raw_path = task_path or plan_path or "/sandbox/example.txt"

        # If the user explicitly requested a path, enforce sandbox boundary on THAT request.
        if task_path is not None:
            norm = _normalize_sandbox_path(task_path)
            # Audit-grade: do not short-circuit. Always call GraphQL so BLOCK attempts are persisted
            # and a real tool_call_id is returned.
            args = {"path": task_path if norm is None else norm}
        else:
            norm = _normalize_sandbox_path(raw_path)
            # Audit-grade: do not short-circuit. Always call GraphQL so BLOCK attempts are persisted.
            args = {"path": raw_path if norm is None else norm}
    elif "fs.write_file" in plan_l or "write" in task.lower():
        tool = "fs.write_file"
        task_path = _extract_path(task)
        plan_path = _extract_path(plan)
        raw_path = task_path or plan_path or "/sandbox/hello.txt"

        content = _extract_write_content(task)

        if task_path is not None:
            norm = _normalize_sandbox_path(task_path)
            args = {
                "path": task_path if norm is None else norm,
                "content": content,
            }
        else:
            norm = _normalize_sandbox_path(raw_path)
            args = {
                "path": raw_path if norm is None else norm,
                "content": content,
            }
    else:
        return state

    # Add attribution metadata (optional for now; useful for audit/leaderboard later)
    args = {**args, "__orchestrator": "langgraph", "__agent_role": "single"}

    payload = {
        "query": PROPOSE_MUTATION,
        "variables": {"tool": tool, "args": args},
    }

    try:
        resp = requests.post(GATEWAY_GRAPHQL_URL, json=payload, timeout=10)
        resp.raise_for_status()
        body = resp.json()
        data = body["data"]["proposeToolCall"]
    except Exception as e:
        tool_decision = {
            "tool_call_id": "n/a",
            "decision": "BLOCK",
            "reason": f"gateway request failed: {e}",
            "result": None,
            "policy_citations": [],
            "incident_refs": [],
            "control_refs": [],
        }
        # Deterministic error surface
        return {**state, "tool_result": f"[ERROR] gateway request failed: {e}", "tool_decision": tool_decision}

    tool_decision = {
        "tool_call_id": data.get("toolCallId", "n/a"),
        "decision": data.get("decision"),
        "reason": data.get("reason"),
        "result": data.get("result"),
        "policy_citations": data.get("policyCitations") or [],
        "incident_refs": data.get("incidentRefs") or [],
        "control_refs": data.get("controlRefs") or [],
    }

    if data["decision"] != "ALLOW":
        # Return tool_result in a uniform way so interpreter can stay consistent
        return {**state, "tool_result": f"[BLOCKED] {data['reason']}", "tool_decision": tool_decision}

    return {**state, "tool_result": data.get("result"), "tool_decision": tool_decision}


def interpreter_node(state: AgentState) -> AgentState:
    """
    Turn tool outputs into a user-facing answer using the same local LLM.
    Ensures the final response always includes a Tool Output line for auditability.
    """
    task = state["user_task"]
    tool_result = state.get("tool_result")

    # If no tool used, still produce a short answer.
    if tool_result is None:
        system = "You are a concise assistant."
        user = (
            f"Task: {task}\n"
            "No tool was used. Provide a short, direct answer or ask one clarifying question if needed."
        )
        final = _llm_text(system, user)
        return {**state, "final_answer": final}

    # Deterministic handling for blocked/error cases.
    if isinstance(tool_result, str) and (tool_result.startswith("[BLOCKED]") or tool_result.startswith("[ERROR]")):
        final = (
            f"Tool Output: {tool_result}\n"
            "I can’t perform that action due to policy restrictions or a gateway error."
        )
        return {**state, "final_answer": final}

    # Normal allowed case: summarize using LLM but include exact tool output string.
    system = "You are a concise assistant. Summarize results clearly."
    user = (
        INTERPRETER_PROMPT.format(tool_result=tool_result)
        + f"\n\nOriginal task: {task}\n\n"
        "You MUST include a line exactly like:\n"
        "Tool Output: <...>\n"
        "Where <...> is the exact tool_result string/object rendered as-is.\n"
    )
    final = _llm_text(system, user)

    if not final:
        final = f"Tool Output: {tool_result}\nCompleted."

    # If model forgets the Tool Output line, enforce it.
    if "tool output:" not in final.lower():
        final = f"Tool Output: {tool_result}\n{final}"

    return {**state, "final_answer": final}


def build_langgraph():
    graph = StateGraph(AgentState)

    graph.add_node("planner", planner_node)
    graph.add_node("tool_proposer", tool_proposer_node)
    graph.add_node("interpreter", interpreter_node)

    graph.set_entry_point("planner")
    graph.add_edge("planner", "tool_proposer")
    graph.add_edge("tool_proposer", "interpreter")
    graph.add_edge("interpreter", END)

    return graph.compile()
