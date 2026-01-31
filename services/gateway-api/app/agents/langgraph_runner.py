from langgraph.graph import StateGraph, END
from .state import AgentState
from .prompts import PLANNER_PROMPT, INTERPRETER_PROMPT
import requests
import os

GATEWAY_GRAPHQL_URL = "http://localhost:8000/graphql"


def planner_node(state: AgentState) -> AgentState:
    # For v1, keep it deterministic
    task = state["user_task"]

    # Simple heuristic (no LLM yet — intentional)
    if "list" in task.lower():
        plan = "Use fs.list_dir to inspect the sandbox"
    elif "read" in task.lower():
        plan = "Use fs.read_file to read a file"
    else:
        plan = "No tool required"

    return {**state, "plan": plan}


def tool_proposer_node(state: AgentState) -> AgentState:
    plan = state["plan"]

    if "fs.list_dir" in plan:
        tool = "fs.list_dir"
        args = {"path": "/sandbox"}
    elif "fs.read_file" in plan:
        tool = "fs.read_file"
        args = {"path": "/sandbox/example.txt"}
    else:
        return state

    query = {
        "query": """
        mutation Propose($tool: String!, $args: JSON!) {
          proposeToolCall(tool: $tool, args: $args) {
            decision
            reason
            result
          }
        }
        """,
        "variables": {"tool": tool, "args": args},
    }

    resp = requests.post(GATEWAY_GRAPHQL_URL, json=query, timeout=5)
    resp.raise_for_status()

    data = resp.json()["data"]["proposeToolCall"]

    if data["decision"] != "ALLOW":
        return {**state, "final_answer": f"Action blocked: {data['reason']}"}

    return {**state, "tool_result": data["result"]}


def interpreter_node(state: AgentState) -> AgentState:
    if not state.get("tool_result"):
        return {**state, "final_answer": "No action required."}

    return {
        **state,
        "final_answer": f"Tool executed successfully. Result: {state['tool_result']}"
    }


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