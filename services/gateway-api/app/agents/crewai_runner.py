import json
import re
import shlex

from crewai import Agent, Task, Crew, Process
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
