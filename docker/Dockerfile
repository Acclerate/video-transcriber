# Video Transcriber Docker 配置
# 多阶段构建：cpu / gpu (NVIDIA CUDA)
#
# 构建:
#   CPU: docker build --target cpu -t video-transcriber -f docker/Dockerfile .
#   GPU: docker build --target gpu -t video-transcriber:gpu -f docker/Dockerfile .

# === CPU 阶段 ===
FROM python:3.10-slim AS cpu

WORKDIR /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 1) 先装 CPU 版 torch（单独一层，利用 Docker 缓存）
RUN pip install --no-cache-dir torch torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

# 2) 剔除 torch/torchaudio 行，装其余依赖（pip 不会重装已满足的 torch）
RUN pip install setuptools wheel \
    && sed '/^torch/d; /^torchaudio/d' requirements.txt > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .
RUN mkdir -p temp logs models_cache output

EXPOSE 8665

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8665/health || exit 1

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8665"]


# === GPU 阶段 ===
FROM python:3.10-slim AS gpu

WORKDIR /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# 1) 先装 CUDA 11.8 版 torch
RUN pip install --no-cache-dir torch torchaudio \
    --index-url https://download.pytorch.org/whl/cu118

# 2) 剔除 torch/torchaudio 行，装其余依赖
RUN pip install setuptools wheel \
    && sed '/^torch/d; /^torchaudio/d' requirements.txt > /tmp/requirements.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt

COPY . .
RUN mkdir -p temp logs models_cache output

EXPOSE 8665

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8665/health || exit 1

CMD ["python", "-m", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8665"]
