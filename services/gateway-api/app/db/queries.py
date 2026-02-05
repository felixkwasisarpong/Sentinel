from sqlalchemy.orm import Session
from .models import Run, ToolCall, Decision, MCPServer, MCPTool

def get_runs(db: Session, limit: int = 50):
    return db.query(Run).order_by(Run.created_at.desc()).limit(limit).all()

def get_run(db: Session, run_id):
    return db.query(Run).filter(Run.id == run_id).first()

def get_tool_calls_for_run(db: Session, run_id):
    return db.query(ToolCall).filter(ToolCall.run_id == run_id).all()

def get_decision_for_tool_call(db: Session, tool_call_id):
    return (
        db.query(Decision)
        .filter(Decision.tool_call_id == tool_call_id)
        .order_by(Decision.created_at.desc())
        .first()
    )

def get_recent_decisions(db: Session, limit: int = 50):
    return db.query(Decision).order_by(Decision.created_at.desc()).limit(limit).all()


def get_mcp_servers(db: Session):
    return db.query(MCPServer).order_by(MCPServer.created_at.desc()).all()


def get_mcp_server_for_tool(db: Session, tool_name: str) -> MCPServer | None:
    if not tool_name:
        return None
    servers = db.query(MCPServer).all()
    best = None
    for server in servers:
        if tool_name.startswith(server.tool_prefix):
            if best is None or len(server.tool_prefix) > len(best.tool_prefix):
                best = server
    return best


def get_mcp_server_by_name(db: Session, name: str) -> MCPServer | None:
    return db.query(MCPServer).filter(MCPServer.name == name).first()


def replace_mcp_tools(db: Session, server_id, tools: list[dict]) -> int:
    db.query(MCPTool).filter(MCPTool.server_id == server_id).delete()
    count = 0
    for tool in tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if not name:
            continue
        db.add(
            MCPTool(
                server_id=server_id,
                name=name,
                description=tool.get("description") if isinstance(tool, dict) else None,
                input_schema=tool.get("inputSchema") if isinstance(tool, dict) else None,
                raw=tool if isinstance(tool, dict) else None,
            )
        )
        count += 1
    return count


def get_mcp_tools_for_server(db: Session, server_id):
    return db.query(MCPTool).filter(MCPTool.server_id == server_id).order_by(MCPTool.name.asc()).all()
