# Video Transcriber Docker 配置

FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p temp logs models_cache

# 设置权限
RUN chmod +x main.py

# 暴露端口
EXPOSE 8665

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8665/health || exit 1

# 启动命令
CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8665"]