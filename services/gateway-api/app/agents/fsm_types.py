from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class FSMState(str, Enum):
    INIT = "INIT"
    PLAN = "PLAN"
    PROPOSE_TOOL = "PROPOSE_TOOL"
    BLOCKED = "BLOCKED"
    EXECUTED = "EXECUTED"
    DONE = "DONE"


@dataclass
class FSMContext:
    user_task: str
    orchestrator: str = "fsm"
    agent_role: str = "single"
    requested_path: Optional[str] = None
    normalized_path: Optional[str] = None
    final_answer: Optional[str] = None

    plan: Optional[str] = None
    tool: Optional[str] = None
    args: Optional[dict] = None
    decision: Optional[str] = None
    result: Optional[str] = None