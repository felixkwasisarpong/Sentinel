import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from strawberry.fastapi import GraphQLRouter
from prometheus_client import make_asgi_app
from .graphql_schema import schema
from .db.base import Base
from .db.session import engine, SessionLocal
from .db.models import MCPServer
from .agents.langgraph_runner import build_langgraph
from .agents.state import AgentState
from .agents.fsm_runner import HybridFSM


from .agents.crewai_runner import run_crewai



langgraph = build_langgraph()



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
    base_url = _normalize_mcp_base(os.getenv("MCP_URL", "http://mcp-sandbox:7001"))
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



@app.post("/agent/run")
def run_agent(task: str):
    initial_state: AgentState = {
        "user_task": task,
        "plan": None,
        "tool_result": None,
        "final_answer": None,
        "tool_decision": None,
    }

    result = langgraph.invoke(initial_state)
    if isinstance(result, dict) and result.get("tool_decision"):
        return result["tool_decision"]
    return {
        "tool_call_id": "n/a",
        "decision": "ALLOW",
        "reason": "No tool required",
        "result": result.get("final_answer") if isinstance(result, dict) else None,
        "policy_citations": [],
        "incident_refs": [],
        "control_refs": [],
    }

@app.post("/agent/fsm/run")
def run_fsm(task: str):
    fsm = HybridFSM(task)
    ctx = fsm.run()
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

@app.post("/agent/crew/run")
def run_crew(task: str):
    return run_crewai(task)
