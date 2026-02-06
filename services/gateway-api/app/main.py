import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter
from prometheus_client import make_asgi_app
from .graphql_schema import schema
from .db.base import Base
from .db.session import engine, SessionLocal
from .db.models import MCPServer
from .mcp_client import validate_mcp_base_url
from .orchestrators.registry import get_orchestrator

app = FastAPI(title="Senteniel Gateway")

# Allow browser-based UI calls to GraphQL/REST.
allowed_origins = [
    o.strip()
    for o in (os.getenv("CORS_ORIGINS", "http://localhost:3000").split(","))
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

Base.metadata.create_all(bind=engine)


def _normalize_mcp_base(url: str) -> str:
    url = (url or "").rstrip("/")
    if url.endswith("/tools"):
        url = url[: -len("/tools")]
    return url


def ensure_default_mcp_server() -> None:
    base_url = _normalize_mcp_base(os.getenv("MCP_BASE_URL") or os.getenv("MCP_URL", "http://mcp-sandbox:7001"))
    base_url = validate_mcp_base_url(base_url)
    name = os.getenv("MCP_DEFAULT_NAME", "sandbox")
    prefix = os.getenv("MCP_DEFAULT_PREFIX", "fs.")

    db = SessionLocal()
    try:
        existing = (
            db.query(MCPServer)
            .filter((MCPServer.name == name) | (MCPServer.tool_prefix == prefix))
            .first()
        )
        if existing:
            existing.base_url = base_url
            existing.name = name
            existing.tool_prefix = prefix
            db.add(existing)
            db.commit()
            return

        server = MCPServer(
            name=name,
            base_url=base_url,
            tool_prefix=prefix,
        )
        db.add(server)
        db.commit()
    finally:
        try:
            db.close()
        except Exception:
            pass


ensure_default_mcp_server()




graphql_app = GraphQLRouter(schema)
app.include_router(graphql_app, prefix="/graphql")

app.mount("/metrics", make_asgi_app())



def _tool_decision_or_default(result: dict | None) -> dict:
    if isinstance(result, dict):
        tool_decision = result.get("tool_decision")
        if tool_decision:
            return tool_decision
        if "final_answer" in result:
            final_answer = result.get("final_answer")
        else:
            final_answer = result.get("result")
    else:
        final_answer = None

    return {
        "tool_call_id": "n/a",
        "decision": "ALLOW",
        "reason": "No tool required",
        "result": final_answer,
        "policy_citations": [],
        "incident_refs": [],
        "control_refs": [],
    }


def _run_orchestrator(task: str, orchestrator_name: str | None) -> dict:
    try:
        orchestrator = get_orchestrator(orchestrator_name)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Unknown orchestrator. Use langgraph, fsm, or crewai.",
        )
    return orchestrator.run(task, sentinel_client_or_core=None, tool_backend=None)


@app.api_route("/agent/run", methods=["GET", "POST"])
def run_agent(task: str, orchestrator: str | None = None):
    orchestrator_name = (orchestrator or os.getenv("ORCHESTRATOR", "langgraph")).strip().lower()
    result = _run_orchestrator(task, orchestrator_name)
    return _tool_decision_or_default(result)

@app.api_route("/agent/fsm/run", methods=["GET", "POST"])
def run_fsm(task: str):
    ctx = _run_orchestrator(task, "fsm_hybrid")
    if isinstance(ctx, dict) and ctx.get("tool_decision"):
        return ctx["tool_decision"]
    return {
        "tool_call_id": "n/a",
        "decision": "ALLOW",
        "reason": "No tool required",
        "result": None,
        "policy_citations": [],
        "incident_refs": [],
        "control_refs": [],
    }

@app.api_route("/agent/crew/run", methods=["GET", "POST"])
def run_crew(task: str):
    return _run_orchestrator(task, "crewai")
