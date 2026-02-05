from __future__ import annotations

from datetime import datetime, timezone
from ..db.models import Run, ToolCall, Decision


def create_run(db, orchestrator: str, agent_id: str) -> Run:
    run = Run(orchestrator=orchestrator, agent_id=agent_id)
    db.add(run)
    db.flush()
    return run


def create_tool_call(db, run_id, tool_name: str, args_redacted: dict) -> ToolCall:
    tool_call = ToolCall(run_id=run_id, tool_name=tool_name, args_redacted=args_redacted)
    db.add(tool_call)
    db.flush()
    return tool_call


def persist_decision(
    db,
    tool_call_id,
    decision: str,
    reason: str,
    risk_score: float | None,
    policy_citations: list[str] | None = None,
    incident_refs: list[str] | None = None,
    control_refs: list[str] | None = None,
) -> Decision:
    decision_row = Decision(
        tool_call_id=tool_call_id,
        decision=decision,
        reason=reason,
        risk_score=risk_score,
    )
    if hasattr(decision_row, "policy_citations"):
        decision_row.policy_citations = policy_citations or []
    if hasattr(decision_row, "incident_refs"):
        decision_row.incident_refs = incident_refs or []
    if hasattr(decision_row, "control_refs"):
        decision_row.control_refs = control_refs or []

    db.add(decision_row)
    return decision_row


def update_tool_call_status(
    db,
    tool_call: ToolCall,
    status: str,
    *,
    approved_at: datetime | None = None,
    approval_note: str | None = None,
    approved_by: str | None = None,
) -> ToolCall:
    tool_call.status = status
    if approved_at is not None:
        tool_call.approved_at = approved_at
    if approval_note is not None:
        tool_call.approval_note = approval_note
    if approved_by is not None and hasattr(tool_call, "approved_by"):
        tool_call.approved_by = approved_by
    db.add(tool_call)
    return tool_call
