import json
import os
import re
import shlex

from crewai import Agent, Task, Crew, Process

GITHUB_DEFAULT_OWNER = os.getenv("GITHUB_OWNER") or os.getenv("GH_OWNER")
GITHUB_DEFAULT_REPO = os.getenv("GITHUB_REPO") or os.getenv("GH_REPO")
from .crewai_tools import FSListDirTool, FSReadFileTool, FSWriteFileTool, propose_tool_decision

# Optional: if crewai_tools.py exposes LAST_TOOL_DECISION, we can attach it for full crew kickoff runs.
try:
    from .crewai_tools import LAST_TOOL_DECISION
except Exception:
    LAST_TOOL_DECISION = None

from app.llm import get_crewai_llm


def _extract_path(task: str) -> str | None:
    match = re.search(r'(/[^\s"\']+)', task)
    return match.group(1) if match else None


def _extract_write_content(task: str) -> str:
    if not task:
        return ""
    m = re.search(r'write\s+(.+?)\s+to\s+(/[^\s"\']+)', task, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"\'')
    m = re.search(r'write\s+(.+?)\s+into\s+(/[^\s"\']+)', task, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"\'')
    m = re.search(r'write\s+(.+)$', task, re.IGNORECASE)
    if m:
        return m.group(1).strip().strip('"\'')
    return ""


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
        try:
            if "." in v:
                args[key] = float(v)
            else:
                args[key] = int(v)
            continue
        except Exception:
            pass
        if (v.startswith("{") and v.endswith("}")) or (v.startswith("[") and v.endswith("]")):
            try:
                args[key] = json.loads(v)
                continue
            except Exception:
                pass
        args[key] = v
    return args


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


def _select_tool(task: str) -> tuple[str, dict] | None:
    task_l = task.lower()

    if any(word in task_l for word in ("list", "show", "display")) and any(
        word in task_l for word in ("file", "files", "dir", "directory", "folder")
    ):
        return "fs.list_dir", {"path": _extract_path(task) or "/sandbox"}

    path = _extract_path(task)
    if "read" in task_l and ("file" in task_l or path):
        return "fs.read_file", {"path": path or "/sandbox/example.txt"}

    if "write" in task_l:
        path = _extract_path(task) or "/sandbox/hello.txt"
        content = _extract_write_content(task)
        return "fs.write_file", {"path": path, "content": content}

    return None


def run_crewai(task: str) -> dict:
    gh = _parse_gh_task(task)
    if gh:
        tool, args = gh
        td = propose_tool_decision(tool, args, "investigator")
        if td.get("decision") == "ALLOW":
            tool_output = td.get("result")
            rendered = f"Tool Output: {tool_output}\nCompleted."
        else:
            tool_output = f"[BLOCKED] {td.get('reason')}"
            rendered = (
                f"Tool Output: {tool_output}\n"
                "I can't perform that action due to policy restrictions."
            )

        return {
            "orchestrator": "crewai",
            "task": task,
            "result": rendered,
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
            "orchestrator": "crewai",
            "task": task,
            "result": f"Tool Output: [BLOCKED] {gh_error}\nI can't perform that action due to policy restrictions.",
            "tool_decision": tool_decision,
        }
    if gh_tool:
        td = propose_tool_decision(gh_tool, gh_args, "investigator")
        if td.get("decision") == "ALLOW":
            tool_output = td.get("result")
            rendered = f"Tool Output: {tool_output}\nCompleted."
        else:
            tool_output = f"[BLOCKED] {td.get('reason')}"
            rendered = (
                f"Tool Output: {tool_output}\n"
                "I can't perform that action due to policy restrictions."
            )
        return {
            "orchestrator": "crewai",
            "task": task,
            "result": rendered,
            "tool_decision": td,
        }

    forced = _select_tool(task)
    if forced:
        tool, args = forced
        td = propose_tool_decision(tool, args, "investigator")

        # Normalize tool output string for the user-facing result line
        if td.get("decision") == "ALLOW":
            tool_output = td.get("result")
            rendered = f"Tool Output: {tool_output}\nCompleted."
        else:
            tool_output = f"[BLOCKED] {td.get('reason')}"
            rendered = (
                f"Tool Output: {tool_output}\n"
                "I can't perform that action due to policy restrictions."
            )

        return {
            "orchestrator": "crewai",
            "task": task,
            "result": rendered,
            "tool_decision": td,
        }

    llm = get_crewai_llm()

    planner = Agent(
        role="Planner",
        goal="Decompose the user request into concrete investigation steps.",
        backstory="You plan safe, minimal actions and avoid unnecessary tool use.",
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    investigator = Agent(
        role="Investigator",
        goal="Gather evidence using only safe, governed tools.",
        backstory="You only use the provided tools and you respect BLOCKED results.",
        tools=[FSListDirTool("investigator"), FSReadFileTool("investigator"), FSWriteFileTool("investigator")],
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    auditor = Agent(
        role="Auditor",
        goal="Check outputs for safety issues and summarize what happened.",
        backstory="You flag policy blocks and suspicious results.",
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    t1 = Task(
        description=f"Create a short plan for: {task}. If tools are needed, say which.",
        expected_output="A 1-3 step plan.",
        agent=planner,
    )

    t2 = Task(
        description=(
            f"User request: {task}\n\n"
            "RULES:\n"
            "- If the user request includes the word 'list', you MUST call the tool `fs_list_dir` exactly once with path \"/sandbox\".\n"
            "- If the user request includes the word 'read' and includes a path, you MUST call the tool `fs_read_file` exactly once with that path.\n"
            "- Return the raw tool output string EXACTLY as received.\n"
            "- If the tool returns a string starting with \"[BLOCKED]\", return that string and STOP.\n"
            "- Do not invent steps or errors.\n"
        ),
        expected_output="Raw tool output (or [BLOCKED] reason) and nothing else.",
        agent=investigator,
    )

    t3 = Task(
        description=(
            "Produce a final answer for the user.\n"
            "You MUST include a line:\n"
            "Tool Output: <...>\n"
            "Where <...> is the EXACT output string from step 2 (e.g., [] or [BLOCKED] ...).\n"
            "Do NOT invent filesystem errors like 'directory does not exist'.\n"
        ),
        expected_output="A short final answer plus the required Tool Output line.",
        agent=auditor,
    )

    crew = Crew(
        agents=[planner, investigator, auditor],
        tasks=[t1, t2, t3],
        process=Process.sequential,
        verbose=False,
    )

    result = crew.kickoff()

    return {
        "orchestrator": "crewai",
        "task": task,
        "result": str(result),
        "tool_decision": LAST_TOOL_DECISION,
    }
