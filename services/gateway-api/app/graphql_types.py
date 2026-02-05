import strawberry
from datetime import datetime
from typing import List, Optional
from strawberry.scalars import JSON

@strawberry.type
class DecisionType:
    decision: str
    reason: str
    created_at: datetime
    policy_citations: List[str]
    incident_refs: List[str]
    control_refs: List[str]


@strawberry.type
class ToolCallType:
    id: str
    tool_name: str
    args_redacted: JSON
    decision: Optional[DecisionType]
    status: Optional[str]
    approved_by: Optional[str]
    approved_at: Optional[datetime]
    approval_note: Optional[str]
    created_at: datetime



@strawberry.type
class RunType:
    id: str
    orchestrator: str
    created_at: datetime
    tool_calls: List[ToolCallType]


@strawberry.type
class MCPServerType:
    id: str
    name: str
    base_url: str
    tool_prefix: str
    created_at: datetime


@strawberry.type
class MCPToolType:
    id: str
    server_id: str
    name: str
    description: str | None
    input_schema: JSON | None
    created_at: datetime


@strawberry.type
class MCPSyncResult:
    server_name: str
    tool_count: int


@strawberry.type
class Query:
    @strawberry.field
    def ping(self) -> str:
        return "pong"
    
