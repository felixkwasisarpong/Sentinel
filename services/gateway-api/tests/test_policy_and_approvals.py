import os
import sys
from pathlib import Path
import uuid

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_gateway_api.db")

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from strawberry.fastapi import GraphQLRouter

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.graphql_schema import schema  # noqa: E402
from app.db.base import Base  # noqa: E402
from app.db.session import engine, SessionLocal  # noqa: E402
from app.db.models import ToolCall, Decision  # noqa: E402


@pytest.fixture(autouse=True)
def _setup_db(monkeypatch):
    os.environ.setdefault("TOOL_BACKEND", "mock")
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(GraphQLRouter(schema), prefix="/graphql")
    return TestClient(app)


def _gql(client, query, variables=None):
    resp = client.post("/graphql", json={"query": query, "variables": variables or {}})
    assert resp.status_code == 200
    payload = resp.json()
    if payload.get("errors"):
        raise AssertionError(payload["errors"])
    return payload["data"]


def test_sandbox_boundary_policy_block_read_outside(client):
    query = """
    mutation Propose($tool: String!, $args: JSON!) {
      proposeToolCall(tool: $tool, args: $args) {
        decision
        reason
        policyCitations
        controlRefs
        incidentRefs
      }
    }
    """
    data = _gql(client, query, {"tool": "fs.read_file", "args": {"path": "/etc/passwd"}})
    decision = data["proposeToolCall"]
    assert decision["decision"] == "BLOCK"
    assert isinstance(decision["policyCitations"], list)
    assert isinstance(decision["controlRefs"], list)
    assert isinstance(decision["incidentRefs"], list)


def test_sandbox_boundary_policy_allow_list_dir(client):
    query = """
    mutation Propose($tool: String!, $args: JSON!) {
      proposeToolCall(tool: $tool, args: $args) {
        decision
        finalStatus
      }
    }
    """
    data = _gql(client, query, {"tool": "fs.list_dir", "args": {"path": "/sandbox"}})
    decision = data["proposeToolCall"]
    assert decision["decision"] == "ALLOW"


def test_approval_flow_write_then_approve_executes_and_persists_result(client):
    propose = """
    mutation Propose($tool: String!, $args: JSON!) {
      proposeToolCall(tool: $tool, args: $args) {
        toolCallId
        decision
        finalStatus
      }
    }
    """
    approve = """
    mutation Approve($id: String!, $note: String, $approvedBy: String) {
      approveToolCall(toolCallId: $id, note: $note, approvedBy: $approvedBy) {
        toolCallId
        decision
        finalStatus
      }
    }
    """

    data = _gql(
        client,
        propose,
        {"tool": "fs.write_file", "args": {"path": "/sandbox/test.txt", "content": "hi"}},
    )
    tool_call_id = data["proposeToolCall"]["toolCallId"]
    assert data["proposeToolCall"]["decision"] == "APPROVAL_REQUIRED"
    assert data["proposeToolCall"]["finalStatus"] == "PENDING"

    data = _gql(client, approve, {"id": tool_call_id, "note": "ok", "approvedBy": "tester"})
    assert data["approveToolCall"]["finalStatus"] == "EXECUTED"

    db = SessionLocal()
    try:
        tc = db.query(ToolCall).filter(ToolCall.id == uuid.UUID(tool_call_id)).first()
        assert tc is not None
        assert tc.status == "EXECUTED"
        assert tc.approved_by == "tester"
        assert tc.result is not None
        decision = (
            db.query(Decision)
            .filter(Decision.tool_call_id == uuid.UUID(tool_call_id))
            .order_by(Decision.created_at.desc())
            .first()
        )
        assert decision is not None
    finally:
        db.close()
