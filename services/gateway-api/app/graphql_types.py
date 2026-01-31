import strawberry
from datetime import datetime
from typing import List, Optional
from strawberry.scalars import JSON

@strawberry.type
class DecisionType:
    decision: str
    reason: str
    created_at: datetime

@strawberry.type
class ToolCallType:
    id: str
    tool_name: str
    args_redacted: JSON
    decision: Optional[DecisionType]

@strawberry.type
class RunType:
    id: str
    orchestrator: str
    created_at: datetime
    tool_calls: List[ToolCallType]