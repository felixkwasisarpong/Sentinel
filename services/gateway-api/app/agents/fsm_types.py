from enum import Enum
from dataclasses import dataclass
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
    plan: Optional[str] = None
    tool: Optional[str] = None
    args: Optional[dict] = None
    decision: Optional[str] = None
    result: Optional[str] = None