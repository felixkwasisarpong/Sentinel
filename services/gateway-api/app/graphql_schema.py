import strawberry
import time
import json
import requests
from typing import Any
from datetime import datetime, timezone

from .policy import evaluate_policy
from .mcp_client import call_tool
from .metrics import tool_calls, decision_latency
from .db.session import SessionLocal
from .db.models import Run, ToolCall as DbToolCall, Decision
from .redaction import redact_args
from .db.queries import (
    get_runs,
    get_run,
    get_tool_calls_for_run,
    get_decision_for_tool_call,
    get_recent_decisions,
)
from .graphql_types import RunType, ToolCallType, DecisionType

# Phase 2A (optional): Neo4j policy graph citations
try:
    from .policy_graph import lookup_policy_ids
except Exception:
    lookup_policy_ids = None


try:
    from strawberry.scalars import JSON as JSONScalar
except Exception:
    from graphql import (
        ObjectValueNode,
        ListValueNode,
        StringValueNode,
        IntValueNode,
        FloatValueNode,
        BooleanValueNode,
        NullValueNode,
        EnumValueNode,
    )

    def _parse_json_literal(node):
        if isinstance(node, ObjectValueNode):
            return {field.name.value: _parse_json_literal(field.value) for field in node.fields}
        if isinstance(node, ListValueNode):
            return [_parse_json_literal(value) for value in node.values]
        if isinstance(node, StringValueNode):
            return node.value
        if isinstance(node, IntValueNode):
            return int(node.value)
        if isinstance(node, FloatValueNode):
            return float(node.value)
        if isinstance(node, BooleanValueNode):
            return node.value
        if isinstance(node, NullValueNode):
            return None
        if isinstance(node, EnumValueNode):
            return node.value
        return None

    JSONScalar = strawberry.scalar(
        Any,
        name="JSON",
        description="Arbitrary JSON value",
        serialize=lambda value: value,
        parse_value=lambda value: value,
        parse_literal=_parse_json_literal,
    )


@strawberry.type
class ToolDecision:
    tool_call_id: str
    decision: str
    reason: str
    result: str | None
    # Phase 2A: citations (empty lists if not available)
    policy_citations: list[str]
    incident_refs: list[str]
    control_refs: list[str]


@strawberry.type
class Mutation:

    @strawberry.mutation
    def propose_tool_call(self, tool: str, args: JSONScalar = "{}") -> ToolDecision:
        db = SessionLocal()
        start = time.time()

        tool_call_id = "n/a"
        try:
            if lookup_policy_ids is None:
                policies, incidents, controls = [], [], []
            else:
                policies, incidents, controls = lookup_policy_ids(tool)
        except Exception:
            policies, incidents, controls = [], [], []

        try:
            # Accept JSON as a string from GraphQL and parse it into a dict
            try:
                parsed_args = json.loads(args) if isinstance(args, str) else args
            except Exception:
                parsed_args = None

            if not isinstance(parsed_args, dict):
                tool_calls.labels(tool=tool, decision="BLOCK").inc()
                decision_latency.observe((time.time() - start) * 1000)

                # Persist run + toolcall + decision even for invalid args
                run = Run(orchestrator="manual", agent_id="manual")
                db.add(run)
                db.flush()

                tool_call = DbToolCall(run_id=run.id, tool_name=tool, args_redacted={"error": "invalid_args"})
                db.add(tool_call)
                db.flush()
                tool_call_id = str(tool_call.id)

                decision = Decision(tool_call_id=tool_call.id, decision="BLOCK", reason="Invalid JSON in args", risk_score=None)
                db.add(decision)
                db.commit()
                return ToolDecision(
                    tool_call_id=tool_call_id,
                    decision="BLOCK",
                    reason="Invalid JSON in args",
                    result=None,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )

            meta_args = {k: v for k, v in parsed_args.items() if str(k).startswith("__")}
            tool_args = {k: v for k, v in parsed_args.items() if not str(k).startswith("__")}

            run = Run(
                orchestrator=meta_args.get("__orchestrator", "manual"),
                agent_id=meta_args.get("__agent_role", "manual"),
            )
            db.add(run)
            db.flush()

            safe_args = redact_args(tool_args)

            # Create tool_call early so we can always attach a Decision row (ALLOW or BLOCK)
            tool_call = DbToolCall(
                run_id=run.id,
                tool_name=tool,
                args_redacted=safe_args,
            )
            db.add(tool_call)
            db.flush()
            tool_call_id = str(tool_call.id)

            allowed, reason, risk_score = evaluate_policy(tool, tool_args)
            if not allowed:
                tool_calls.labels(tool=tool, decision="BLOCK").inc()
                decision_latency.observe((time.time() - start) * 1000)

                decision = Decision(
                    tool_call_id=tool_call.id,
                    decision="BLOCK",
                    reason=reason,
                    risk_score=risk_score,
                )
                # Persist citations if Decision model supports these columns
                if hasattr(decision, "policy_citations"):
                    decision.policy_citations = policies
                if hasattr(decision, "incident_refs"):
                    decision.incident_refs = incidents
                if hasattr(decision, "control_refs"):
                    decision.control_refs = controls

                db.add(decision)
                db.commit()
                return ToolDecision(
                    tool_call_id=tool_call_id,
                    decision="BLOCK",
                    reason=reason,
                    result=None,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )

            # Allowed: execute tool via MCP
            try:
                result = call_tool(tool, tool_args)
            except requests.RequestException as exc:
                detail = None
                if getattr(exc, "response", None) is not None:
                    try:
                        detail = exc.response.json().get("detail")
                    except Exception:
                        detail = exc.response.text

                tool_calls.labels(tool=tool, decision="BLOCK").inc()
                decision_latency.observe((time.time() - start) * 1000)

                reason_text = detail or str(exc)
                if not detail:
                    reason_text = f"Tool call failed: {reason_text}"

                decision = Decision(
                    tool_call_id=tool_call.id,
                    decision="BLOCK",
                    reason=reason_text,
                    risk_score=risk_score,
                )
                if hasattr(decision, "policy_citations"):
                    decision.policy_citations = policies
                if hasattr(decision, "incident_refs"):
                    decision.incident_refs = incidents
                if hasattr(decision, "control_refs"):
                    decision.control_refs = controls

                db.add(decision)
                db.commit()
                return ToolDecision(
                    tool_call_id=tool_call_id,
                    decision="BLOCK",
                    reason=reason_text,
                    result=None,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )

            result_value = result.get("result") if isinstance(result, dict) and "result" in result else result
            if isinstance(result_value, (dict, list)):
                result_text = json.dumps(result_value)
            else:
                result_text = str(result_value)

            tool_calls.labels(tool=tool, decision="ALLOW").inc()
            decision_latency.observe((time.time() - start) * 1000)

            decision = Decision(
                tool_call_id=tool_call.id,
                decision="ALLOW",
                reason=reason,
                risk_score=risk_score,
            )
            if hasattr(decision, "policy_citations"):
                decision.policy_citations = policies
            if hasattr(decision, "incident_refs"):
                decision.incident_refs = incidents
            if hasattr(decision, "control_refs"):
                decision.control_refs = controls

            db.add(decision)
            db.commit()

            return ToolDecision(
                tool_call_id=tool_call_id,
                decision="ALLOW",
                reason=reason,
                result=result_text,
                policy_citations=policies,
                incident_refs=incidents,
                control_refs=controls,
            )

        finally:
            try:
                db.close()
            except Exception:
                pass

    @strawberry.mutation
    def approve_tool_call(self, tool_call_id: str, note: str | None = None) -> ToolDecision:
        db = SessionLocal()
        try:
            tool_call = db.query(DbToolCall).filter(DbToolCall.id == tool_call_id).first()
            if not tool_call:
                return ToolDecision(
                    tool_call_id="n/a",
                    decision="BLOCK",
                    reason="Tool call not found",
                    result=None,
                    policy_citations=[],
                    incident_refs=[],
                    control_refs=[],
                )

            if tool_call.status != "PENDING":
                return ToolDecision(
                    tool_call_id=str(tool_call.id),
                    decision="BLOCK",
                    reason=f"Tool call is not pending (status={tool_call.status})",
                    result=None,
                    policy_citations=[],
                    incident_refs=[],
                    control_refs=[],
                )

            # Mark approved
            tool_call.status = "APPROVED"
            tool_call.approved_at = datetime.now(timezone.utc)
            tool_call.approval_note = note
            db.add(tool_call)
            db.flush()

            # Execute tool with stored args (redacted)
            try:
                result = call_tool(tool_call.tool_name, tool_call.args_redacted or {})
                result_value = result.get("result") if isinstance(result, dict) and "result" in result else result
                if isinstance(result_value, (dict, list)):
                    result_text = json.dumps(result_value)
                else:
                    result_text = str(result_value)
                decision_value = "ALLOW"
                reason_text = "Approved"
            except requests.RequestException as exc:
                detail = None
                if getattr(exc, "response", None) is not None:
                    try:
                        detail = exc.response.json().get("detail")
                    except Exception:
                        detail = exc.response.text
                reason_text = detail or str(exc)
                if not detail:
                    reason_text = f"Tool call failed: {reason_text}"
                result_text = None
                decision_value = "BLOCK"

            # Persist decision
            prior = get_decision_for_tool_call(db, tool_call.id)
            risk_score = getattr(prior, "risk_score", 0.0) if prior else 0.0
            decision = Decision(
                tool_call_id=tool_call.id,
                decision=decision_value,
                reason=reason_text,
                risk_score=risk_score,
            )
            db.add(decision)

            # Mark executed
            tool_call.status = "EXECUTED"
            db.add(tool_call)
            db.commit()

            try:
                if lookup_policy_ids is None:
                    policies, incidents, controls = [], [], []
                else:
                    policies, incidents, controls = lookup_policy_ids(tool_call.tool_name)
            except Exception:
                policies, incidents, controls = [], [], []

            return ToolDecision(
                tool_call_id=str(tool_call.id),
                decision=decision_value,
                reason=reason_text,
                result=result_text,
                policy_citations=policies,
                incident_refs=incidents,
                control_refs=controls,
            )
        finally:
            try:
                db.close()
            except Exception:
                pass

    @strawberry.mutation
    def deny_tool_call(self, tool_call_id: str, note: str | None = None) -> ToolDecision:
        db = SessionLocal()
        try:
            tool_call = db.query(DbToolCall).filter(DbToolCall.id == tool_call_id).first()
            if not tool_call:
                return ToolDecision(
                    tool_call_id="n/a",
                    decision="BLOCK",
                    reason="Tool call not found",
                    result=None,
                    policy_citations=[],
                    incident_refs=[],
                    control_refs=[],
                )

            if tool_call.status != "PENDING":
                return ToolDecision(
                    tool_call_id=str(tool_call.id),
                    decision="BLOCK",
                    reason=f"Tool call is not pending (status={tool_call.status})",
                    result=None,
                    policy_citations=[],
                    incident_refs=[],
                    control_refs=[],
                )

            tool_call.status = "DENIED"
            tool_call.approved_at = datetime.now(timezone.utc)
            tool_call.approval_note = note
            db.add(tool_call)
            db.flush()

            prior = get_decision_for_tool_call(db, tool_call.id)
            risk_score = getattr(prior, "risk_score", 0.0) if prior else 0.0
            decision = Decision(
                tool_call_id=tool_call.id,
                decision="BLOCK",
                reason=note or "Denied",
                risk_score=risk_score,
            )
            db.add(decision)
            db.commit()

            try:
                if lookup_policy_ids is None:
                    policies, incidents, controls = [], [], []
                else:
                    policies, incidents, controls = lookup_policy_ids(tool_call.tool_name)
            except Exception:
                policies, incidents, controls = [], [], []

            return ToolDecision(
                tool_call_id=str(tool_call.id),
                decision="BLOCK",
                reason=note or "Denied",
                result=None,
                policy_citations=policies,
                incident_refs=incidents,
                control_refs=controls,
            )
        finally:
            try:
                db.close()
            except Exception:
                pass


@strawberry.type
class Query:
    def _resolve_citations(self, decision: Decision | None, tool_name: str) -> tuple[list[str], list[str], list[str]]:
        if decision is not None and hasattr(decision, "policy_citations"):
            policies = getattr(decision, "policy_citations", []) or []
            incidents = getattr(decision, "incident_refs", []) or []
            controls = getattr(decision, "control_refs", []) or []
            return policies, incidents, controls

        if lookup_policy_ids is None:
            return [], [], []

        try:
            return lookup_policy_ids(tool_name)
        except Exception:
            return [], [], []

    @strawberry.field
    def ping(self) -> str:
        return "pong"
    
    @strawberry.field
    def runs(self, limit: int = 20) -> list[RunType]:
        db = SessionLocal()
        runs = get_runs(db, limit)
        result = []

        for r in runs:
            result.append(
                RunType(
                    id=str(r.id),
                    orchestrator=r.orchestrator,
                    created_at=r.created_at,
                    tool_calls=[]
                )
            )

        db.close()
        return result

    @strawberry.field
    def run(self, id: str) -> RunType | None:
        db = SessionLocal()
        run = get_run(db, id)
        if not run:
            db.close()
            return None

        tool_calls = []
        for tc in get_tool_calls_for_run(db, run.id):
            decision = get_decision_for_tool_call(db, tc.id)
            policies, incidents, controls = self._resolve_citations(decision, tc.tool_name)
            tool_calls.append(
                ToolCallType(
                    id=str(tc.id),
                    tool_name=tc.tool_name,
                    args_redacted=tc.args_redacted,
                    created_at=tc.created_at,
                    decision=DecisionType(
                        decision=decision.decision,
                        reason=decision.reason,
                        created_at=decision.created_at,
                        policy_citations=policies,
                        incident_refs=incidents,
                        control_refs=controls,
                    ) if decision else None
                )
            )

        result = RunType(
            id=str(run.id),
            orchestrator=run.orchestrator,
            created_at=run.created_at,
            tool_calls=tool_calls,
        )
        db.close()
        return result

    @strawberry.field
    def decisions(self, limit: int = 20) -> list[DecisionType]:
        db = SessionLocal()
        decisions = get_recent_decisions(db, limit)
        result = [
            DecisionType(
                decision=d.decision,
                reason=d.reason,
                created_at=d.created_at,
                policy_citations=[],
                incident_refs=[],
                control_refs=[],
            )
            for d in decisions
        ]
        db.close()
        return result

    @strawberry.field(name="pendingApprovals")
    def pending_approvals(self, limit: int = 20) -> list[ToolCallType]:
        db = SessionLocal()
        tool_calls = (
            db.query(DbToolCall)
            .order_by(DbToolCall.created_at.desc())
            .all()
        )

        results: list[ToolCallType] = []
        for tc in tool_calls:
            decision = get_decision_for_tool_call(db, tc.id)
            if not decision or decision.decision != "APPROVAL_REQUIRED":
                continue

            policies, incidents, controls = self._resolve_citations(decision, tc.tool_name)

            results.append(
                ToolCallType(
                    id=str(tc.id),
                    tool_name=tc.tool_name,
                    args_redacted=tc.args_redacted,
                    created_at=tc.created_at,
                    decision=DecisionType(
                        decision=decision.decision,
                        reason=decision.reason,
                        created_at=decision.created_at,
                        policy_citations=policies,
                        incident_refs=incidents,
                        control_refs=controls,
                    ),
                )
            )
            if len(results) >= limit:
                break

        db.close()
        return results

schema = strawberry.Schema(query=Query, mutation=Mutation)
