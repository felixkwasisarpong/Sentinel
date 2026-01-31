from typing import Dict, Any, Optional,TypedDict




class AgentState(TypedDict):
    user_task: str
    plan: Optional[str]
    tool_result: Optional[str]
    final_answer: Optional[str]