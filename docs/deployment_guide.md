# Video Transcriber 部署指南

本文档详细说明如何在不同环境中部署Video Transcriber短视频转文本工具。

## 📋 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [环境配置](#环境配置)
- [部署方式](#部署方式)
  - [本地开发部署](#本地开发部署)
  - [Docker部署](#docker部署)
  - [云服务器部署](#云服务器部署)
  - [容器编排部署](#容器编排部署)
- [性能优化](#性能优化)
- [监控与日志](#监控与日志)
- [故障排除](#故障排除)

## 🔧 系统要求

### 最低配置
- **CPU**: 2核心
- **内存**: 4GB RAM
- **存储**: 10GB 可用空间
- **网络**: 稳定的互联网连接

### 推荐配置
- **CPU**: 4核心以上
- **内存**: 8GB RAM以上
- **存储**: 50GB 可用空间
- **GPU**: NVIDIA GPU (可选，用于加速)

### 软件依赖
- **Python**: 3.10+
- **FFmpeg**: 最新版本
- **Docker**: 20.10+ (可选)
- **Docker Compose**: 2.0+ (可选)

## 🚀 快速开始

### 1. 克隆项目
```bash
git clone https://github.com/yourusername/video-transcriber.git
cd video-transcriber
```

### 2. 环境配置
```bash
# 复制环境配置文件
cp .env.example .env

# 编辑配置文件
nano .env
```

### 3. 安装依赖
```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装Python依赖
pip install -r requirements.txt

# 安装FFmpeg (Ubuntu/Debian)
sudo apt update && sudo apt install ffmpeg

# 安装FFmpeg (CentOS/RHEL)
sudo yum install epel-release
sudo yum install ffmpeg

# 安装FFmpeg (macOS)
brew install ffmpeg
```

### 4. 启动服务
```bash
# 命令行模式
python webmain.py --help

# Web服务模式
python webmain.py serve --host 0.0.0.0 --port 8665

# 或使用uvicorn直接启动
uvicorn api.apimain:app --host 0.0.0.0 --port 8665
```

## ⚙️ 环境配置

### 环境变量说明

```bash
# 服务配置
HOST=0.0.0.0                    # 服务监听地址
PORT=8665                       # 服务端口
DEBUG=false                     # 调试模式

# SenseVoice模型配置
DEFAULT_MODEL=sensevoice-small  # 默认模型
ENABLE_GPU=true                 # 启用GPU加速
MODEL_CACHE_DIR=./models_cache  # 模型缓存目录

# 文件配置
TEMP_DIR=./temp                 # 临时文件目录
MAX_FILE_SIZE=100               # 最大文件大小(MB)
CLEANUP_AFTER=3600              # 清理间隔(秒)

# 日志配置
LOG_LEVEL=INFO                  # 日志级别
LOG_FILE=./logs/app.log         # 日志文件
LOG_TO_CONSOLE=true             # 控制台输出

# API配置
API_KEY=                        # API密钥(可选)
CORS_ORIGINS=*                  # CORS设置
RATE_LIMIT_PER_MINUTE=60        # 速率限制
```

### GPU支持配置

如果有NVIDIA GPU，可以启用GPU加速：

```bash
# 检查CUDA是否可用
python -c "import torch; print(torch.cuda.is_available())"

# 安装CUDA版本的PyTorch
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118

# 在.env中启用GPU
ENABLE_GPU=true
```

## 🐳 部署方式

### 本地开发部署

适合开发和测试环境：

```bash
# 1. 设置开发环境
cp .env.example .env
# 编辑.env文件，设置DEBUG=true

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动开发服务器
python webmain.py serve --reload

# 4. 访问服务
# Web界面: http://localhost:8665
# API文档: http://localhost:8665/docs
```

### Docker部署

推荐的生产环境部署方式：

```bash
# 1. 构建镜像
docker build -f docker/Dockerfile -t video-transcriber:latest .

# 2. 运行容器
docker run -d \
  --name video-transcriber \
  -p 8665:8665 \
  -v $(pwd)/logs:/app/logs \
  -v $(pwd)/temp:/app/temp \
  -v $(pwd)/models_cache:/app/models_cache \
  -v $(pwd)/.env:/app/.env:ro \
  video-transcriber:latest

# 3. 查看日志
docker logs -f video-transcriber

# 4. 进入容器
docker exec -it video-transcriber bash
```

### Docker Compose部署

更便捷的容器化部署：

```bash
# 1. 启动所有服务
docker-compose -f docker/docker-compose.yml up -d

# 2. 查看服务状态
docker-compose -f docker/docker-compose.yml ps

# 3. 查看日志
docker-compose -f docker/docker-compose.yml logs -f

# 4. 停止服务
docker-compose -f docker/docker-compose.yml down

# 开发环境
docker-compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up

# 生产环境
docker-compose -f docker/docker-compose.yml -f docker/docker-compose.prod.yml up -d
```

### 云服务器部署

#### AWS EC2部署

```bash
# 1. 创建EC2实例
# - 选择Ubuntu 20.04 LTS
# - 实例类型: t3.medium 或更高
# - 存储: 至少20GB

# 2. 连接到实例
ssh -i your-key.pem ubuntu@your-ec2-ip

# 3. 安装Docker
sudo apt update
sudo apt install docker.io docker-compose
sudo usermod -aG docker ubuntu

# 4. 部署应用
git clone https://github.com/yourusername/video-transcriber.git
cd video-transcriber
cp .env.example .env
# 编辑.env配置

docker-compose -f docker/docker-compose.yml up -d

# 5. 配置防火墙
sudo ufw allow 8665
sudo ufw enable
```

#### 阿里云ECS部署

```bash
# 1. 创建ECS实例
# - 镜像: CentOS 7.9
# - 实例规格: ecs.c5.large 或更高
# - 系统盘: 40GB

# 2. 安装依赖
sudo yum update -y
sudo yum install -y docker git
sudo systemctl start docker
sudo systemctl enable docker

# 3. 安装Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.12.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# 4. 部署应用
git clone https://github.com/yourusername/video-transcriber.git
cd video-transcriber
cp .env.example .env
# 配置.env文件

sudo docker-compose -f docker/docker-compose.yml up -d

# 5. 配置安全组
# 在阿里云控制台开放8665端口
```

### Kubernetes部署

企业级容器编排部署：

```yaml
# k8s/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: video-transcriber

---
# k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: video-transcriber
  namespace: video-transcriber
spec:
  replicas: 3
  selector:
    matchLabels:
      app: video-transcriber
  template:
    metadata:
      labels:
        app: video-transcriber
    spec:
      containers:
      - name: video-transcriber
        image: video-transcriber:latest
        ports:
        - containerPort: 8665
        env:
        - name: HOST
          value: "0.0.0.0"
        - name: PORT
          value: "8665"
        resources:
          requests:
            memory: "2Gi"
            cpu: "1000m"
          limits:
            memory: "4Gi"
            cpu: "2000m"
        volumeMounts:
        - name: temp-storage
          mountPath: /app/temp
        - name: models-cache
          mountPath: /app/models_cache
      volumes:
      - name: temp-storage
        emptyDir: {}
      - name: models-cache
        persistentVolumeClaim:
          claimName: models-cache-pvc

---
# k8s/service.yaml
apiVersion: v1
kind: Service
metadata:
  name: video-transcriber-service
  namespace: video-transcriber
spec:
  selector:
    app: video-transcriber
  ports:
  - port: 80
    targetPort: 8665
  type: LoadBalancer
```

部署到Kubernetes：

```bash
# 创建命名空间和资源
kubectl apply -f k8s/

# 查看部署状态
kubectl get pods -n video-transcriber
kubectl get services -n video-transcriber

# 查看日志
kubectl logs -f deployment/video-transcriber -n video-transcriber
```

## 🔧 性能优化

### 1. 硬件优化

```bash
# GPU加速配置
export CUDA_VISIBLE_DEVICES=0
export PYTORCH_CUDA_ALLOC_CONF=max_split_size_mb:512

# 内存优化
export OMP_NUM_THREADS=4
export MKL_NUM_THREADS=4
```

### 2. 应用优化

```python
# .env配置优化
DEFAULT_MODEL=sensevoice-small   # SenseVoice模型
MAX_CONCURRENT_DOWNLOADS=3       # 控制并发数
CLEANUP_AFTER=1800              # 更频繁清理
```

### 3. 系统优化

```bash
# 增加文件描述符限制
echo "* soft nofile 65536" >> /etc/security/limits.conf
echo "* hard nofile 65536" >> /etc/security/limits.conf

# 优化内核参数
echo "vm.max_map_count=262144" >> /etc/sysctl.conf
echo "net.core.somaxconn=65535" >> /etc/sysctl.conf
sysctl -p
```

## 📊 监控与日志

### 日志配置

```bash
# 查看应用日志
tail -f logs/app.log

# Docker日志
docker logs -f video-transcriber

# 系统日志
journalctl -u video-transcriber -f
```

### 监控指标

添加Prometheus监控：

```yaml
# docker-compose.monitoring.yml
version: '3.8'

services:
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    volumes:
      - grafana-data:/var/lib/grafana

volumes:
  grafana-data:
```

### 健康检查

```bash
# 应用健康检查
curl http://localhost:8665/health

# 系统资源检查
htop
df -h
free -h
```

## 🔧 故障排除

### 常见问题

#### 1. 模型下载失败
```bash
# 检查网络连接
ping huggingface.co

# 手动下载模型
python webmain.py download-model sensevoice-small

# 设置代理
export HTTP_PROXY=http://proxy:8080
export HTTPS_PROXY=http://proxy:8080
```

#### 2. 内存不足
```bash
# 检查内存使用
free -h
docker stats

# 减少并发数
MAX_CONCURRENT_TASKS=1
```

#### 3. GPU不可用
```bash
# 检查CUDA
nvidia-smi
python -c "import torch; print(torch.cuda.is_available())"

# 重新安装PyTorch
pip uninstall torch torchaudio
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

#### 4. 端口被占用
```bash
# 查看端口占用
netstat -tlnp | grep 8665
lsof -i :8665

# 杀死占用进程
sudo kill -9 <PID>

# 更改端口
PORT=8666
```

### 日志分析

```bash
# 查看错误日志
grep ERROR logs/app.log

# 监控API调用
grep "POST /api" logs/app.log | tail -20

# 性能分析
grep "processing_time" logs/app.log | awk '{print $NF}' | sort -n
```

### 备份与恢复

```bash
# 备份配置
tar -czf backup-$(date +%Y%m%d).tar.gz .env logs/ models_cache/

# 恢复配置
tar -xzf backup-20240829.tar.gz

# 数据库备份(如果使用)
docker exec video-transcriber-redis redis-cli save
```

## 🚀 扩展部署

### 负载均衡

使用Nginx进行负载均衡：

```nginx
# nginx.conf
upstream video_transcriber {
    server 127.0.0.1:8666;
    server 127.0.0.1:8667;
    server 127.0.0.1:8668;
}

server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://video_transcriber;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 自动化部署

使用GitHub Actions自动部署：

```yaml
# .github/workflows/deploy.yml
name: Deploy to Production

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
    - uses: actions/checkout@v3
    
    - name: Deploy to server
      uses: appleboy/ssh-action@v0.1.5
      with:
        host: ${{ secrets.HOST }}
        username: ${{ secrets.USERNAME }}
        key: ${{ secrets.SSH_KEY }}
        script: |
          cd /opt/video-transcriber
          git pull origin main
          docker-compose down
          docker-compose up -d --build
```

现在您的Video Transcriber已经可以在各种环境中成功部署了！🎉