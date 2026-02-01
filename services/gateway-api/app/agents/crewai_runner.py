import re

from crewai import Agent, Task, Crew, Process
from .crewai_tools import FSListDirTool, FSReadFileTool, propose_tool_decision
from app.llm import get_crewai_llm  # <-- add this


def _extract_path(task: str) -> str | None:
    match = re.search(r'(/[^\s"\']+)', task)
    return match.group(1) if match else None


def _select_tool(task: str) -> tuple[str, dict] | None:
    task_l = task.lower()

    if any(word in task_l for word in ("list", "show", "display")) and any(
        word in task_l for word in ("file", "files", "dir", "directory", "folder")
    ):
        return "fs.list_dir", {"path": _extract_path(task) or "/sandbox"}

    path = _extract_path(task)
    if "read" in task_l and ("file" in task_l or path):
        return "fs.read_file", {"path": path or "/sandbox/example.txt"}

    return None


def run_crewai(task: str) -> dict:
    forced = _select_tool(task)
    if forced:
        tool, args = forced
        return propose_tool_decision(tool, args, "investigator")

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
        tools=[FSListDirTool("investigator"), FSReadFileTool("investigator")],
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
        "tool_call_id": "n/a",
        "decision": "ALLOW",
        "reason": "No tool required",
        "result": str(result),
        "policy_citations": [],
        "incident_refs": [],
        "control_refs": [],
    }
