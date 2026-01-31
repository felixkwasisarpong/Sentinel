PLANNER_PROMPT = """
You are a planning agent.

Given a user task, decide whether a tool is required.
If so, describe WHICH tool and WHY.
Do not execute anything.

Task:
{task}
"""

INTERPRETER_PROMPT = """
Given the tool result below, produce a concise, user-facing answer.

Tool result:
{tool_result}
"""