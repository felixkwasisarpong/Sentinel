from __future__ import annotations

from ..agents.langgraph_runner import build_langgraph
from ..agents.state import AgentState


class LangGraphOrchestrator:
    name = "langgraph"

    def __init__(self) -> None:
        self._graph = build_langgraph()

    def run(
        self,
        task: str,
        *,
        sentinel_client_or_core=None,
        tool_backend=None,
    ) -> dict:
        initial_state: AgentState = {
            "user_task": task,
            "plan": None,
            "tool_result": None,
            "final_answer": None,
            "tool_decision": None,
        }
        return self._graph.invoke(initial_state)
