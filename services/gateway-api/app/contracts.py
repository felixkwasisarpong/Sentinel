from pydantic import BaseModel
from typing import Dict, Any

class ToolCall(BaseModel):
    tool: str
    args: Dict[str, Any]