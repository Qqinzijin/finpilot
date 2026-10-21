"""
FastAPI 应用入口
对应 Spring Boot 的 Application.java + Controller
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .schemas import ChatRequest, ChatResponse, ErrorResponse
from .services import chat_service

from fastapi.responses import StreamingResponse

# ============================================================
# 创建应用
# ============================================================
app = FastAPI(
    title="FinPilot API",
    description="基于 LangGraph 的多 Agent 个人理财助手 API",
    version="0.1.0",
)

# ============================================================
# CORS 配置（让 Streamlit 前端能调用）
# ============================================================
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发期允许所有来源；上线时应改成具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# 路由
# ============================================================
@app.get("/", tags=["health"])
def read_root():
    """根路径"""
    return {"app": "FinPilot", "version": "0.1.0"}


@app.get("/health", tags=["health"])
def health_check():
    """健康检查"""
    return {"status": "ok"}


@app.post(
    "/chat",
    response_model=ChatResponse,
    responses={500: {"model": ErrorResponse}},
    tags=["chat"],
    summary="多 Agent 对话",
    description="向 FinPilot 发送一条消息，由 Supervisor 决定调度哪些子 Agent，最终返回整合后的回复。",
)
def chat(request: ChatRequest) -> ChatResponse:
    try:
        # 把 history（HistoryMessage 列表）传给 service
        response = chat_service.chat(
            user_message=request.message,
            history=request.history,
        )
        return response
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"处理对话时发生错误: {str(e)}",
        )

@app.post(
    "/chat/stream",
    tags=["chat"],
    summary="多 Agent 流式对话",
    description="通过 SSE 流式返回 Agent 思考过程与最终回复",
)
async def chat_stream(request: ChatRequest):
    return StreamingResponse(
        chat_service.chat_stream(
            user_message=request.message,
            history=request.history,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )