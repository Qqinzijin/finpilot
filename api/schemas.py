"""
API 数据契约（DTO）
对应 Spring Boot 的 Request/Response DTO
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from typing import Optional, List, Literal


# ============================================================
# 请求 DTO
# ============================================================
class HistoryMessage(BaseModel):
    """对话历史中的单条消息"""
    role: Literal["user", "assistant"] = Field(description="消息角色")
    content: str = Field(description="消息内容")


class ChatRequest(BaseModel):
    """对话请求"""
    message: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="用户输入的消息内容（当前这一条）",
        examples=["贵州茅台现在多少钱？"],
    )
    history: List[HistoryMessage] = Field(
        default_factory=list,
        description="对话历史（不包含当前消息）。空数组表示新对话",
    )

# ============================================================
# 响应 DTO
# ============================================================
class AgentTrace(BaseModel):
    """单次 Agent 调用的执行追踪信息"""
    agent_name: str = Field(description="被调度的 Agent 名称")
    task: Optional[str] = Field(default=None, description="子任务描述")


class ChatResponse(BaseModel):
    """对话响应"""
    reply: str = Field(description="LLM 最终回复内容")
    agents_used: List[str] = Field(
        default_factory=list,
        description="本次请求涉及到的 Agent 列表",
    )
    iterations: int = Field(
        default=0,
        description="Supervisor 总共思考了几轮",
    )


# ============================================================
# 错误响应 DTO
# ============================================================
class ErrorResponse(BaseModel):
    """统一错误响应"""
    error: str
    detail: Optional[str] = None


# ============================================================
# SSE Streaming 事件 DTO
# ============================================================
from enum import Enum

class StreamEventType(str, Enum):
    """SSE 事件类型枚举"""
    AGENT_ROUTING = "agent_routing"      # Supervisor 决定调度某 Agent
    AGENT_COMPLETED = "agent_completed"  # 子 Agent 完成工作
    FINAL_REPLY = "final_reply"          # 最终回复
    DONE = "done"                        # 流结束
    ERROR = "error"                      # 错误事件


class StreamEvent(BaseModel):
    """SSE 事件的统一结构"""
    type: StreamEventType
    data: dict = Field(default_factory=dict, description="事件携带的数据")