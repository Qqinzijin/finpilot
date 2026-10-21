"""
Hello FastAPI: 最小可运行的 FastAPI 应用
目的：先理解 FastAPI 的最基本结构
"""
from fastapi import FastAPI

# 创建 FastAPI 应用实例
app = FastAPI(
    title="FinPilot Hello API",
    description="最小测试版本",
)


# 第一个端点：根路径
@app.get("/")
def read_root():
    """访问 / 时返回的内容"""
    return {"message": "Hello FinPilot!"}


# 第二个端点：健康检查
@app.get("/health")
def health_check():
    """让外部检查服务是否在跑"""
    return {"status": "ok"}


# 第三个端点：演示 POST + 参数
from pydantic import BaseModel

class EchoRequest(BaseModel):
    """请求体的"契约"——必须包含 message 字段"""
    message: str

@app.post("/echo")
def echo(request: EchoRequest):
    """收到什么就回什么"""
    return {"you_said": request.message}