import requests
from .fsm_types import FSMState, FSMContext

GATEWAY_GRAPHQL_URL = "http://localhost:8000/graphql"


class FSMRunner:
    def __init__(self, task: str):
        self.state = FSMState.INIT
        self.ctx = FSMContext(user_task=task)

    def run(self) -> FSMContext:
        while self.state != FSMState.DONE:
            if self.state == FSMState.INIT:
                self.state = FSMState.PLAN

            elif self.state == FSMState.PLAN:
                self._plan()
                self.state = FSMState.PROPOSE_TOOL

            elif self.state == FSMState.PROPOSE_TOOL:
                self._propose_tool()

            elif self.state in (FSMState.BLOCKED, FSMState.EXECUTED):
                self.state = FSMState.DONE

        return self.ctx

    def _plan(self):
        task = self.ctx.user_task.lower()

        if "list" in task:
            self.ctx.plan = "List sandbox files"
            self.ctx.tool = "fs.list_dir"
            self.ctx.args = {"path": "/sandbox"}
        elif "read" in task:
            self.ctx.plan = "Read sandbox file"
            self.ctx.tool = "fs.read_file"
            self.ctx.args = {"path": "/sandbox/example.txt"}
        else:
            self.ctx.plan = "No tool required"
            self.state = FSMState.DONE

    def _propose_tool(self):
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
            "variables": {
                "tool": self.ctx.tool,
                "args": self.ctx.args,
            },
        }

        resp = requests.post(GATEWAY_GRAPHQL_URL, json=query, timeout=5)
        resp.raise_for_status()

        data = resp.json()["data"]["proposeToolCall"]
        self.ctx.decision = data["decision"]

        if data["decision"] != "ALLOW":
            self.ctx.result = data["reason"]
            self.state = FSMState.BLOCKED
        else:
            self.ctx.result = data["result"]
            self.state = FSMState.EXECUTED