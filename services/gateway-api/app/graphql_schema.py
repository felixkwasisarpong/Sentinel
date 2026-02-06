import strawberry
import time
import json
import requests
import uuid
from typing import Any
from datetime import datetime, timezone

from .mcp_client import list_tools, validate_mcp_base_url
from .metrics import tool_calls, decision_latency
from .tool_backends.registry import get_tool_backend
from .core.audit import (
    create_run,
    create_tool_call,
    persist_decision,
    update_tool_call_result,
    update_tool_call_status,
)
from .core.policy_engine import evaluate_tool_call
from .core.policy_graph import get_citations_for_decision
from .db.session import SessionLocal
from .db.models import ToolCall as DbToolCall, Decision, MCPServer
from .redaction import redact_args
from .db.queries import (
    get_runs,
    get_run,
    get_tool_calls_for_run,
    get_decision_for_tool_call,
    get_recent_decisions,
    get_mcp_servers,
    get_mcp_server_by_name,
    replace_mcp_tools,
    get_mcp_tools_for_server,
)
from .graphql_types import RunType, ToolCallType, DecisionType, MCPServerType, MCPToolType, MCPSyncResult

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
    final_status: str | None
    # Phase 2A: citations (empty lists if not available)
    policy_citations: list[str]
    incident_refs: list[str]
    control_refs: list[str]


def _coerce_uuid(value: str):
    try:
        return uuid.UUID(value)
    except Exception:
        return value


@strawberry.type
class Mutation:

    @strawberry.mutation
    def propose_tool_call(self, tool: str, args: JSONScalar = "{}") -> ToolDecision:
        db = SessionLocal()
        start = time.time()

        tool_call_id = "n/a"

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
                run = create_run(db, orchestrator="manual", agent_id="manual")
                tool_call = create_tool_call(db, run.id, tool, {"error": "invalid_args"})
                tool_call_id = str(tool_call.id)

                policies, incidents, controls = get_citations_for_decision(tool, {})
                persist_decision(
                    db,
                    tool_call.id,
                    decision="BLOCK",
                    reason="Invalid JSON in args",
                    risk_score=None,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )
                db.commit()
                return ToolDecision(
                    tool_call_id=tool_call_id,
                    decision="BLOCK",
                    reason="Invalid JSON in args",
                    result=None,
                    final_status=None,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )

            meta_args = {k: v for k, v in parsed_args.items() if str(k).startswith("__")}
            tool_args = {k: v for k, v in parsed_args.items() if not str(k).startswith("__")}

            run = create_run(
                db,
                orchestrator=meta_args.get("__orchestrator", "manual"),
                agent_id=meta_args.get("__agent_role", "manual"),
            )

            safe_args = redact_args(tool_args)

            # Create tool_call early so we can always attach a Decision row (ALLOW or BLOCK)
            tool_call = create_tool_call(db, run.id, tool, safe_args)
            tool_call_id = str(tool_call.id)

            decision_payload = evaluate_tool_call(
                tool,
                tool_args,
                context={
                    "orchestrator": run.orchestrator,
                    "agent_id": run.agent_id,
                },
            )
            decision_value = decision_payload.decision
            reason = decision_payload.reason
            risk_score = decision_payload.risk_score
            policies = decision_payload.policy_citations
            incidents = decision_payload.incident_refs
            controls = decision_payload.control_refs
            if decision_value == "APPROVAL_REQUIRED":
                tool_calls.labels(tool=tool, decision="APPROVAL_REQUIRED").inc()
                decision_latency.observe((time.time() - start) * 1000)

                update_tool_call_status(db, tool_call, "PENDING")
                persist_decision(
                    db,
                    tool_call.id,
                    decision="APPROVAL_REQUIRED",
                    reason=reason,
                    risk_score=risk_score,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )
                db.commit()
                return ToolDecision(
                    tool_call_id=tool_call_id,
                    decision="APPROVAL_REQUIRED",
                    reason=reason,
                    result=None,
                    final_status="PENDING",
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )

            if decision_value != "ALLOW":
                tool_calls.labels(tool=tool, decision="BLOCK").inc()
                decision_latency.observe((time.time() - start) * 1000)

                persist_decision(
                    db,
                    tool_call.id,
                    decision=decision_value,
                    reason=reason,
                    risk_score=risk_score,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )
                db.commit()
                return ToolDecision(
                    tool_call_id=tool_call_id,
                    decision=decision_value,
                    reason=reason,
                    result=None,
                    final_status=None,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )

            # Allowed: execute tool via ToolBackend
            try:
                tool_backend = get_tool_backend()
                result = tool_backend.call_tool(tool, tool_args)
            except Exception as exc:
                detail = None
                if isinstance(exc, requests.RequestException):
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

                persist_decision(
                    db,
                    tool_call.id,
                    decision="BLOCK",
                    reason=reason_text,
                    risk_score=risk_score,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )
                db.commit()
                return ToolDecision(
                    tool_call_id=tool_call_id,
                    decision="BLOCK",
                    reason=reason_text,
                    result=None,
                    final_status=None,
                    policy_citations=policies,
                    incident_refs=incidents,
                    control_refs=controls,
                )

            result_value = result.get("result") if isinstance(result, dict) and "result" in result else result
            if isinstance(result_value, (dict, list)):
                result_text = json.dumps(result_value)
            else:
                result_text = str(result_value)

            update_tool_call_result(db, tool_call, result_text)
            update_tool_call_status(db, tool_call, "EXECUTED")

            tool_calls.labels(tool=tool, decision="ALLOW").inc()
            decision_latency.observe((time.time() - start) * 1000)

            persist_decision(
                db,
                tool_call.id,
                decision="ALLOW",
                reason=reason,
                risk_score=risk_score,
                policy_citations=policies,
                incident_refs=incidents,
                control_refs=controls,
            )
            db.commit()

            return ToolDecision(
                tool_call_id=tool_call_id,
                decision="ALLOW",
                reason=reason,
                result=result_text,
                final_status=None,
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
    def approve_tool_call(
        self,
        tool_call_id: str,
        note: str | None = None,
        approved_by: str | None = None,
    ) -> ToolDecision:
        db = SessionLocal()
        try:
            tool_call_id_value = _coerce_uuid(tool_call_id)
            tool_call = db.query(DbToolCall).filter(DbToolCall.id == tool_call_id_value).first()
            if not tool_call:
                return ToolDecision(
                    tool_call_id="n/a",
                    decision="BLOCK",
                    reason="Tool call not found",
                    result=None,
                    final_status=None,
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
                    final_status=None,
                    policy_citations=[],
                    incident_refs=[],
                    control_refs=[],
                )

            # Mark approved
            update_tool_call_status(
                db,
                tool_call,
                "APPROVED",
                approved_at=datetime.now(timezone.utc),
                approval_note=note,
                approved_by=approved_by or "manual",
            )
            db.flush()

            # Execute tool with stored args (redacted) via ToolBackend
            try:
                tool_backend = get_tool_backend()
                result = tool_backend.call_tool(tool_call.tool_name, tool_call.args_redacted or {})
                result_value = result.get("result") if isinstance(result, dict) and "result" in result else result
                if isinstance(result_value, (dict, list)):
                    result_text = json.dumps(result_value)
                else:
                    result_text = str(result_value)
                decision_value = "ALLOW"
                reason_text = "Approved"
            except Exception as exc:
                detail = None
                if isinstance(exc, requests.RequestException):
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

            update_tool_call_result(db, tool_call, result_text)

            # Persist decision
            prior = get_decision_for_tool_call(db, tool_call.id)
            risk_score = getattr(prior, "risk_score", 0.0) if prior else 0.0
            policies, incidents, controls = get_citations_for_decision(tool_call.tool_name, tool_call.args_redacted)
            persist_decision(
                db,
                tool_call.id,
                decision=decision_value,
                reason=reason_text,
                risk_score=risk_score,
                policy_citations=policies,
                incident_refs=incidents,
                control_refs=controls,
            )

            # Mark executed
            update_tool_call_status(db, tool_call, "EXECUTED")
            db.commit()

            return ToolDecision(
                tool_call_id=str(tool_call.id),
                decision=decision_value,
                reason=reason_text,
                result=result_text,
                final_status=tool_call.status,
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
    def deny_tool_call(
        self,
        tool_call_id: str,
        note: str | None = None,
        approved_by: str | None = None,
    ) -> ToolDecision:
        db = SessionLocal()
        try:
            tool_call_id_value = _coerce_uuid(tool_call_id)
            tool_call = db.query(DbToolCall).filter(DbToolCall.id == tool_call_id_value).first()
            if not tool_call:
                return ToolDecision(
                    tool_call_id="n/a",
                    decision="BLOCK",
                    reason="Tool call not found",
                    result=None,
                    final_status=None,
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
                    final_status=None,
                    policy_citations=[],
                    incident_refs=[],
                    control_refs=[],
                )

            update_tool_call_status(
                db,
                tool_call,
                "DENIED",
                approved_at=datetime.now(timezone.utc),
                approval_note=note,
                approved_by=approved_by or "manual",
            )
            db.flush()

            prior = get_decision_for_tool_call(db, tool_call.id)
            db.commit()

            policies, incidents, controls = get_citations_for_decision(tool_call.tool_name, tool_call.args_redacted)

            decision_value = getattr(prior, "decision", None) or "APPROVAL_REQUIRED"
            reason_value = note or getattr(prior, "reason", None) or "Denied"

            return ToolDecision(
                tool_call_id=str(tool_call.id),
                decision=decision_value,
                reason=reason_value,
                result=None,
                final_status="DENIED",
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
    def register_mcp_server(
        self,
        name: str,
        base_url: str,
        tool_prefix: str,
        auth_header: str | None = None,
        auth_token: str | None = None,
    ) -> MCPServerType:
        db = SessionLocal()
        try:
            base_url = validate_mcp_base_url(base_url)
            existing = (
                db.query(MCPServer)
                .filter((MCPServer.name == name) | (MCPServer.tool_prefix == tool_prefix))
                .first()
            )

            if existing:
                existing.name = name
                existing.base_url = base_url
                existing.tool_prefix = tool_prefix
                existing.auth_header = auth_header
                existing.auth_token = auth_token
                db.add(existing)
                db.commit()
                return MCPServerType(
                    id=str(existing.id),
                    name=existing.name,
                    base_url=existing.base_url,
                    tool_prefix=existing.tool_prefix,
                    created_at=existing.created_at,
                )

            server = MCPServer(
                name=name,
                base_url=base_url,
                tool_prefix=tool_prefix,
                auth_header=auth_header,
                auth_token=auth_token,
            )
            db.add(server)
            db.commit()
            db.refresh(server)
            return MCPServerType(
                id=str(server.id),
                name=server.name,
                base_url=server.base_url,
                tool_prefix=server.tool_prefix,
                created_at=server.created_at,
            )
        finally:
            try:
                db.close()
            except Exception:
                pass

    @strawberry.mutation
    def sync_mcp_tools(self, server_name: str) -> MCPSyncResult:
        db = SessionLocal()
        try:
            server = get_mcp_server_by_name(db, server_name)
            if not server:
                raise ValueError(f"MCP server not found: {server_name}")

            tools = list_tools(server.base_url, server.auth_header, server.auth_token)
            count = replace_mcp_tools(db, server.id, tools)
            db.commit()
            return MCPSyncResult(server_name=server.name, tool_count=count)
        finally:
            try:
                db.close()
            except Exception:
                pass


def _resolve_citations(decision: Decision | None, tool_name: str) -> tuple[list[str], list[str], list[str]]:
    if decision is not None and hasattr(decision, "policy_citations"):
        policies = getattr(decision, "policy_citations", []) or []
        incidents = getattr(decision, "incident_refs", []) or []
        controls = getattr(decision, "control_refs", []) or []
        return policies, incidents, controls

    return get_citations_for_decision(tool_name)


@strawberry.type
class Query:
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
                    tool_calls=[],
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
            policies, incidents, controls = _resolve_citations(decision, tc.tool_name)
            tool_calls.append(
                ToolCallType(
                    id=str(tc.id),
                    tool_name=tc.tool_name,
                    args_redacted=tc.args_redacted,
                    created_at=tc.created_at,
                    status=tc.status,
                    approved_by=getattr(tc, "approved_by", None),
                    approved_at=tc.approved_at,
                    approval_note=tc.approval_note,
                    result=getattr(tc, "result", None),
                    decision=DecisionType(
                        decision=decision.decision,
                        reason=decision.reason,
                        created_at=decision.created_at,
                        policy_citations=policies,
                        incident_refs=incidents,
                        control_refs=controls,
                    ) if decision else None,
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
            .filter(DbToolCall.status == "PENDING")
            .order_by(DbToolCall.created_at.desc())
            .limit(limit * 3)
            .all()
        )

        results: list[ToolCallType] = []
        for tc in tool_calls:
            decision = get_decision_for_tool_call(db, tc.id)
            if not decision or decision.decision != "APPROVAL_REQUIRED":
                continue

            policies, incidents, controls = _resolve_citations(decision, tc.tool_name)

            results.append(
                ToolCallType(
                    id=str(tc.id),
                    tool_name=tc.tool_name,
                    args_redacted=tc.args_redacted,
                    status=tc.status,
                    approved_by=getattr(tc, "approved_by", None),
                    approved_at=tc.approved_at,
                    approval_note=tc.approval_note,
                    result=getattr(tc, "result", None),
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

    @strawberry.field(name="mcpServers")
    def mcp_servers(self) -> list[MCPServerType]:
        db = SessionLocal()
        servers = get_mcp_servers(db)
        result = [
            MCPServerType(
                id=str(s.id),
                name=s.name,
                base_url=s.base_url,
                tool_prefix=s.tool_prefix,
                created_at=s.created_at,
            )
            for s in servers
        ]
        db.close()
        return result

    @strawberry.field(name="mcpTools")
    def mcp_tools(self, server_name: str) -> list[MCPToolType]:
        db = SessionLocal()
        server = get_mcp_server_by_name(db, server_name)
        if not server:
            db.close()
            return []

        tools = get_mcp_tools_for_server(db, server.id)
        result = [
            MCPToolType(
                id=str(t.id),
                server_id=str(t.server_id),
                name=t.name,
                description=t.description,
                input_schema=t.input_schema,
                created_at=t.created_at,
            )
            for t in tools
        ]
        db.close()
        return result

schema = strawberry.Schema(query=Query, mutation=Mutation)
