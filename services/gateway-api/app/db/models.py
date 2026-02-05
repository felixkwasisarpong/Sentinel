import uuid
from sqlalchemy import Column, String, DateTime, ForeignKey, JSON, Float
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func
from .base import Base
from sqlalchemy import Text


class Run(Base):
    __tablename__ = "runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    orchestrator = Column(String, nullable=False)
    agent_id = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class ToolCall(Base):
    __tablename__ = "tool_calls"  
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id = Column(UUID(as_uuid=True), ForeignKey("runs.id"))
    tool_name = Column(String, nullable=False)
    args_redacted = Column(JSON, nullable=False)
    status = Column(String, nullable=False, default="EXECUTED")
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approval_note = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Decision(Base):
    __tablename__ = "decisions"
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tool_call_id = Column(UUID(as_uuid=True), ForeignKey("tool_calls.id"))
    decision = Column(String, nullable=False)
    reason = Column(String, nullable=False)
    risk_score = Column(Float, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MCPServer(Base):
    __tablename__ = "mcp_servers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String, nullable=False, unique=True)
    base_url = Column(String, nullable=False)
    tool_prefix = Column(String, nullable=False, unique=True)
    auth_header = Column(String, nullable=True)
    auth_token = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class MCPTool(Base):
    __tablename__ = "mcp_tools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    server_id = Column(UUID(as_uuid=True), ForeignKey("mcp_servers.id"), nullable=False)
    name = Column(String, nullable=False)
    description = Column(String, nullable=True)
    input_schema = Column(JSON, nullable=True)
    raw = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
