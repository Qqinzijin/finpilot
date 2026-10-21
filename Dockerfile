# ===========================================
# FinPilot Docker Image
# 单容器双进程：FastAPI（内部 8000）+ Streamlit（对外 7860）
# 用 supervisord 管理两个进程
# ===========================================

# 1. 基础镜像：Python 3.11 slim 版（轻量，体积小）
FROM python:3.11-slim

# 2. 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    API_BASE_URL=http://127.0.0.1:8000

# 3. 安装系统依赖（supervisor + 编译工具）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        supervisor \
        curl \
    && rm -rf /var/lib/apt/lists/*

# 4. 工作目录
WORKDIR /app

# 5. 先复制 requirements.txt 再 install——利用 Docker 缓存
COPY requirements.txt .
RUN pip install -r requirements.txt

# 6. 复制项目代码
COPY . .

# 7. 复制 supervisord 配置
COPY supervisord.conf /etc/supervisor/conf.d/supervisord.conf

# 8. 暴露端口（HF Spaces 必须 7860）
EXPOSE 7860

# 9. 容器启动命令：跑 supervisord 管理多进程
CMD ["/usr/bin/supervisord", "-c", "/etc/supervisor/conf.d/supervisord.conf"]