from sqlalchemy.orm import Session
from .models import Run, ToolCall, Decision

def get_runs(db: Session, limit: int = 50):
    return db.query(Run).order_by(Run.created_at.desc()).limit(limit).all()

def get_run(db: Session, run_id):
    return db.query(Run).filter(Run.id == run_id).first()

def get_tool_calls_for_run(db: Session, run_id):
    return db.query(ToolCall).filter(ToolCall.run_id == run_id).all()

def get_decision_for_tool_call(db: Session, tool_call_id):
    return db.query(Decision).filter(Decision.tool_call_id == tool_call_id).first()

def get_recent_decisions(db: Session, limit: int = 50):
    return db.query(Decision).order_by(Decision.created_at.desc()).limit(limit).all()