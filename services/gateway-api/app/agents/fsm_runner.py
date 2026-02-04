import os
import re
import requests

from .fsm_types import FSMState, FSMContext

# Use env override so this works both inside Docker and on host.
GATEWAY_GRAPHQL_URL = os.getenv("GATEWAY_GRAPHQL_URL", "http://localhost:8000/graphql")

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


def _extract_path(text: str) -> str | None:
    """Extract an absolute path from free-form text, stopping at whitespace/quotes."""
    if not text:
        return None
    m = re.search(r'(/[^\s"\']+)', text)
    return m.group(1) if m else None


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


class HybridFSM:
    """
    Hybrid FSM orchestrator:
    - Multi-role phases: planner -> investigator -> auditor
    - Deterministic control-flow (no LLM decides whether tools run)
    - All tool execution is governed via Senteniel GraphQL -> MCP.
    """

    def __init__(self, user_task: str):
        self.ctx = FSMContext(user_task=user_task)
        # Distinguish hybrid in logs/leaderboard
        self.ctx.orchestrator = "fsm_hybrid"
        self.state = FSMState.INIT
        # Full GraphQL ToolDecision payload (snake_case) for UI/leaderboard
        self.ctx.tool_decision = None

    def run(self) -> dict:
        while self.state not in (FSMState.DONE,):
            if self.state == FSMState.INIT:
                self.state = FSMState.PLAN

            elif self.state == FSMState.PLAN:
                self._plan()

            elif self.state == FSMState.PROPOSE_TOOL:
                self._propose_tool()

            elif self.state in (FSMState.BLOCKED, FSMState.EXECUTED):
                self._audit()

            else:
                self.state = FSMState.DONE

        return {
            "final_state": {
                "orchestrator": self.ctx.orchestrator,
                "agent_role": self.ctx.agent_role,
                "user_task": self.ctx.user_task,
                "requested_path": self.ctx.requested_path,
                "normalized_path": self.ctx.normalized_path,
                "plan": self.ctx.plan,
                "tool": self.ctx.tool,
                "args": self.ctx.args,
                "decision": self.ctx.decision,
                "result": self.ctx.result,
            },
            "final_answer": getattr(self.ctx, "final_answer", None),
            "tool_decision": getattr(self.ctx, "tool_decision", None),
        }

    # ---- Role: Planner ----
    def _plan(self) -> None:
        self.ctx.agent_role = "planner"
        task_l = (self.ctx.user_task or "").lower()

        # LIST
        if "list" in task_l:
            requested = _extract_path(self.ctx.user_task) or "/sandbox"
            norm = _normalize_sandbox_path(requested)

            self.ctx.plan = "List sandbox files" if requested == "/sandbox" else f"List files in {requested}"
            self.ctx.tool = "fs.list_dir"
            self.ctx.requested_path = requested
            self.ctx.normalized_path = norm

            if _extract_path(self.ctx.user_task) is not None and norm is None:
                self.ctx.decision = "BLOCK"
                self.ctx.result = "[BLOCKED] path must be under /sandbox"
                self.ctx.tool_decision = {
                    "tool_call_id": "n/a",
                    "decision": "BLOCK",
                    "reason": "path must be under /sandbox",
                    "result": None,
                    "policy_citations": [],
                    "incident_refs": [],
                    "control_refs": [],
                }
                self.state = FSMState.BLOCKED
                return

            safe_path = norm or "/sandbox"
            self.ctx.args = {
                "path": safe_path,
                "__orchestrator": self.ctx.orchestrator,
                "__agent_role": self.ctx.agent_role,
            }
            self.state = FSMState.PROPOSE_TOOL
            return

        # READ
        if "read" in task_l:
            requested = _extract_path(self.ctx.user_task) or "/sandbox/example.txt"
            norm = _normalize_sandbox_path(requested)

            self.ctx.requested_path = requested
            self.ctx.normalized_path = norm
            self.ctx.plan = f"Read file {requested}"
            self.ctx.tool = "fs.read_file"

            # Audit-grade: do not short-circuit. Always call GraphQL so BLOCK attempts are persisted
            # and return a real tool_call_id.
            # If out-of-sandbox, pass the raw requested path; gateway policy will BLOCK and log it.
            safe_path = requested if norm is None else norm
            self.ctx.args = {
                "path": safe_path,
                "__orchestrator": self.ctx.orchestrator,
                "__agent_role": self.ctx.agent_role,
            }
            self.state = FSMState.PROPOSE_TOOL
            return

        # WRITE
        if "write" in task_l:
            requested = _extract_path(self.ctx.user_task) or "/sandbox/hello.txt"
            norm = _normalize_sandbox_path(requested)

            self.ctx.requested_path = requested
            self.ctx.normalized_path = norm
            self.ctx.plan = f"Write file {requested}"
            self.ctx.tool = "fs.write_file"

            if _extract_path(self.ctx.user_task) is not None and norm is None:
                self.ctx.decision = "BLOCK"
                self.ctx.result = "[BLOCKED] path must be under /sandbox"
                self.ctx.tool_decision = {
                    "tool_call_id": "n/a",
                    "decision": "BLOCK",
                    "reason": "path must be under /sandbox",
                    "result": None,
                    "policy_citations": [],
                    "incident_refs": [],
                    "control_refs": [],
                }
                self.state = FSMState.BLOCKED
                return

            safe_path = norm or "/sandbox/hello.txt"
            content = _extract_write_content(self.ctx.user_task)
            self.ctx.args = {
                "path": safe_path,
                "content": content,
                "__orchestrator": self.ctx.orchestrator,
                "__agent_role": self.ctx.agent_role,
            }
            self.state = FSMState.PROPOSE_TOOL
            return

        # NO TOOL
        self.ctx.plan = "No tool required"
        self.ctx.decision = "ALLOW"
        self.ctx.result = ""
        self.state = FSMState.DONE

    # ---- Role: Investigator ----
    def _propose_tool(self) -> None:
        self.ctx.agent_role = "investigator"

        if not self.ctx.tool:
            self.state = FSMState.DONE
            return

        # Enforce sandbox boundary for filesystem tools
        if self.ctx.tool in ("fs.list_dir", "fs.read_file", "fs.write_file"):
            raw = None
            if isinstance(self.ctx.args, dict):
                raw = self.ctx.args.get("path")

            norm = _normalize_sandbox_path(raw)

            # Audit-grade: do not short-circuit. Always call GraphQL so BLOCK attempts are persisted.
            # If out-of-sandbox, pass raw path through; policy will BLOCK and log it.

            self.ctx.args = {
                **(self.ctx.args or {}),
                "path": raw if norm is None else norm,
                "__orchestrator": self.ctx.orchestrator,
                "__agent_role": self.ctx.agent_role,
            }

        payload = {
            "query": PROPOSE_MUTATION,
            "variables": {"tool": self.ctx.tool, "args": self.ctx.args or {}},
        }

        resp = requests.post(GATEWAY_GRAPHQL_URL, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()["data"]["proposeToolCall"]

        tool_decision = {
            "tool_call_id": data.get("toolCallId", "n/a"),
            "decision": data.get("decision"),
            "reason": data.get("reason"),
            "result": data.get("result"),
            "policy_citations": data.get("policyCitations") or [],
            "incident_refs": data.get("incidentRefs") or [],
            "control_refs": data.get("controlRefs") or [],
        }
        self.ctx.tool_decision = tool_decision

        if data["decision"] != "ALLOW":
            self.ctx.decision = "BLOCK"
            self.ctx.result = f"[BLOCKED] {data['reason']}"
            self.state = FSMState.BLOCKED
            return

        self.ctx.decision = "ALLOW"
        self.ctx.result = data.get("result")
        self.state = FSMState.EXECUTED

    # ---- Role: Auditor ----
    def _audit(self) -> None:
        self.ctx.agent_role = "auditor"

        # Deterministic, audit-friendly formatting.
        if isinstance(self.ctx.result, str) and (
            self.ctx.result.startswith("[BLOCKED]") or self.ctx.result.startswith("[ERROR]")
        ):
            self.ctx.final_answer = (
                f"Tool Output: {self.ctx.result}\n"
                "I can’t perform that action due to policy restrictions."
            )
        else:
            self.ctx.final_answer = f"Tool Output: {self.ctx.result}\nCompleted."

        self.state = FSMState.DONE


def run_fsm(user_task: str) -> dict:
    """Entrypoint used by the API layer."""
    return HybridFSM(user_task).run()
