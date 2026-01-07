# Video Transcriber 🎥➡️📝

一个强大的视频文件转文本工具，基于OpenAI Whisper实现高精度语音识别。

![Python](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-green.svg)
![Whisper](https://img.shields.io/badge/whisper-OpenAI-orange.svg)

## ✨ 特性

- 📤 **文件上传**: 直接上传视频文件进行处理
- 🤖 **高精度转录**: 基于OpenAI Whisper，准确率95%+
- 🔒 **隐私保护**: 本地处理，数据不外泄
- 🌐 **Web界面**: 简洁易用的Web界面
- ⚡ **批量处理**: 支持多个视频同时转录
- 🎵 **智能音频**: 自动提取和优化音频质量
- 📝 **多种格式**: 支持JSON、TXT、SRT、VTT输出
- 🔄 **实时状态**: 实时显示处理进度

## 🚀 快速开始

### 环境要求

- Python 3.8+
- FFmpeg (用于音视频处理)
- 4GB+ RAM (推荐8GB以上)
- GPU (可选，用于加速)

### 安装

1. **克隆项目**
```bash
git clone https://github.com/Acclerate/video-transcriber.git
cd video-transcriber
```

2. **安装依赖**
```bash
# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装Python依赖
pip install -r requirements.txt

# 安装FFmpeg (Ubuntu/Debian)
sudo apt update
sudo apt install ffmpeg

# 安装FFmpeg (macOS)
brew install ffmpeg

# 安装FFmpeg (Windows)
# 下载并安装: https://ffmpeg.org/download.html
```

3. **启动服务**
```bash
# 启动Web服务
python main.py serve
```

## 📖 使用方法

### Web界面使用

1. 启动服务:
```bash
python main.py serve
```

2. 访问 `http://localhost:8000`

3. 使用方式:
   - **单个转录**: 上传视频文件，选择模型和语言，点击开始转录
   - **批量转录**: 一次上传多个视频文件（最多10个），自动批量处理

### API 使用

```bash
# 启动API服务
uvicorn api.main:app --host 0.0.0.0 --port 8000

# 访问API文档
# http://localhost:8000/docs
```

```python
import requests

# 单个文件转录
files = {"file": open("video.mp4", "rb")}
data = {
    "model": "small",
    "language": "auto",
    "with_timestamps": True,
    "output_format": "json"
}
response = requests.post("http://localhost:8000/api/v1/transcribe", files=files, data=data)

result = response.json()
print(result["data"]["transcription"]["text"])

# 批量转录
files = [("files", open(f"video{i}.mp4", "rb")) for i in range(3)]
data = {
    "model": "small",
    "language": "auto",
    "max_concurrent": 3
}
response = requests.post("http://localhost:8000/api/v1/batch-transcribe", files=files, data=data)
```

### 命令行使用

```bash
# 基础转录
python main.py transcribe /path/to/video.mp4

# 指定Whisper模型
python main.py transcribe /path/to/video.mp4 --model small

# 包含时间戳
python main.py transcribe /path/to/video.mp4 --timestamps

# 批量处理
python main.py batch file_list.txt

# 指定输出格式
python main.py transcribe /path/to/video.mp4 --format srt

# 查看系统信息
python main.py info

# 查看可用模型
python main.py models
```

## 🛠️ 配置选项

### Whisper模型选择

| 模型 | 大小 | 速度 | 准确率 | 推荐场景 |
|------|------|------|--------|----------|
| tiny | 39MB | 最快 | 一般 | 快速预览 |
| base | 74MB | 快 | 良好 | 日常使用 |
| small | 244MB | 中等 | 很好 | **推荐** |
| medium | 769MB | 慢 | 优秀 | 高质量需求 |
| large | 1550MB | 最慢 | 最佳 | 专业场景 |

### 支持的视频格式

| 格式 | 扩展名 | 状态 |
|------|--------|------|
| MP4 | .mp4, .m4v | ✅ |
| AVI | .avi | ✅ |
| MKV | .mkv | ✅ |
| MOV | .mov | ✅ |
| WMV | .wmv | ✅ |
| FLV | .flv | ✅ |
| WebM | .webm | ✅ |

### 环境变量配置

创建 `.env` 文件:

```env
# 服务配置
HOST=0.0.0.0
PORT=8000
DEBUG=false

# Whisper配置
DEFAULT_MODEL=small
ENABLE_GPU=true

# 文件配置
TEMP_DIR=./temp
MAX_FILE_SIZE=500MB
CLEANUP_AFTER=3600

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=./logs/app.log

# CORS配置
CORS_ORIGINS=*
```

## 📁 项目结构

```
video-transcriber/
├── 📄 README.md
├── 📄 requirements.txt
├── 📄 main.py                  # 命令行入口
├── 📁 api/                     # Web API
│   ├── 📄 main.py             # FastAPI应用
│   └── 📄 websocket.py        # WebSocket处理
├── 📁 core/                    # 核心模块
│   ├── 📄 __init__.py
│   ├── 📄 engine.py           # 核心引擎
│   ├── 📄 downloader.py       # 音频提取
│   └── 📄 transcriber.py      # 语音转录
├── 📁 models/                  # 数据模型
│   ├── 📄 __init__.py
│   └── 📄 schemas.py          # Pydantic模型
├── 📁 utils/                   # 工具函数
│   ├── 📄 __init__.py
│   ├── 📄 logger.py           # 日志工具
│   └── 📄 helpers.py          # 辅助函数
├── 📁 web/                     # Web前端
│   ├── 📄 index.html
│   ├── 📄 style.css
│   └── 📄 script.js
└── 📁 tests/                   # 测试文件
```

## ⚡ 性能指标

### 处理速度 (基于Whisper Small模型)
- **短视频** (0-1分钟): ~10-20秒
- **中等视频** (1-5分钟): ~30-60秒
- **长视频** (5-10分钟): ~1-3分钟

### 准确率
- **中文**: 95%+
- **英文**: 97%+
- **中英混合**: 92%+

### 资源消耗
- **CPU**: 2-4核推荐
- **内存**: 4GB+ (Small模型)
- **GPU**: 可选，3倍加速效果
- **磁盘**: 临时文件约50-200MB/视频

## 📝 API 端点

### 核心端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/api/v1/transcribe` | POST | 上传文件转录 |
| `/api/v1/batch-transcribe` | POST | 批量转录（多文件上传） |
| `/api/v1/status/{task_id}` | GET | 查询任务状态 |
| `/api/v1/batch-status/{batch_id}` | GET | 查询批量任务状态 |
| `/api/v1/models` | GET | 获取可用模型 |
| `/api/v1/stats` | GET | 获取统计信息 |
| `/api/v1/cleanup` | POST | 清理临时文件 |
| `/ws/transcribe` | WS | WebSocket实时转录 |

### 请求示例

```bash
# 单个文件转录
curl -X POST "http://localhost:8000/api/v1/transcribe" \
  -F "file=@video.mp4" \
  -F "model=small" \
  -F "language=auto" \
  -F "output_format=json"

# 批量转录
curl -X POST "http://localhost:8000/api/v1/batch-transcribe" \
  -F "files=@video1.mp4" \
  -F "files=@video2.mp4" \
  -F "model=small" \
  -F "max_concurrent=3"
```

## 🔧 开发指南

### 开发环境搭建

```bash
# 安装开发依赖
pip install -r requirements.txt

# 运行测试
pytest

# 代码格式化
black .
isort .

# 类型检查
mypy .
```

### 项目架构

```
┌─────────────────────────────────────────┐
│              用户输入层                  │
│       Web Upload / WebSocket            │
└────────────┬────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────┐
│            核心引擎层                    │
│     VideoTranscriptionEngine           │
│  - 任务管理                             │
│  - 进度追踪                             │
│  - 批量处理                             │
└────────────┬────────────────────────────┘
             │
     ┌───────┴────────┐
     │                │
     ▼                ▼
┌──────────┐    ┌──────────────┐
│音频提取器 │    │  语音转录器   │
│Extractor │    │  Transcriber │
│          │    │   (Whisper)  │
└──────────┘    └──────────────┘
     │                │
     └────────┬───────┘
              ▼
     ┌────────────────┐
     │  转录结果输出   │
     │  TXT/JSON/SRT  │
     └────────────────┘
```

## 🐛 故障排除

### 常见问题

**1. FFmpeg未找到**
```bash
# 确认FFmpeg已安装
ffmpeg -version

# Ubuntu/Debian安装
sudo apt install ffmpeg

# macOS安装
brew install ffmpeg

# 添加到PATH环境变量
export PATH=$PATH:/path/to/ffmpeg
```

**2. 文件上传失败**
- 检查文件大小是否超过500MB
- 确认文件格式为视频格式
- 检查网络连接

**3. 转录准确率低**
- 尝试更大的Whisper模型
- 检查音频质量
- 确认语言设置正确

**4. 内存不足**
- 使用更小的Whisper模型 (tiny/base)
- 减少并发处理数量
- 增加系统内存

**5. GPU加速不生效**
```bash
# 检查CUDA可用性
python -c "import torch; print(torch.cuda.is_available())"

# 安装CUDA支持的PyTorch
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

### 性能优化

**1. GPU加速**
```bash
# 安装CUDA支持的PyTorch
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118
```

**2. 模型缓存**
```python
# 预下载模型
import whisper
model = whisper.load_model("small")
```

**3. 批量处理并发数调整**
```bash
# API调用时调整
curl -X POST "http://localhost:8000/api/v1/batch-transcribe" \
  -F "files=@video1.mp4" \
  -F "files=@video2.mp4" \
  -F "max_concurrent=5"
```

## 🐳 Docker 使用

### 构建镜像

```bash
docker build -t video-transcriber .
```

### 运行容器

```bash
# 基础运行
docker run -p 8000:8000 video-transcriber

# 使用GPU
docker run --gpus all -p 8000:8000 video-transcriber
```

### Docker Compose

```yaml
version: '3.8'
services:
  video-transcriber:
    build: .
    ports:
      - "8000:8000"
    environment:
      - ENABLE_GPU=true
      - DEFAULT_MODEL=small
    restart: unless-stopped
```

## 🤝 贡献指南

欢迎贡献代码！请遵循以下步骤：

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交改动 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [OpenAI Whisper](https://github.com/openai/whisper) - 强大的语音识别模型
- [FastAPI](https://fastapi.tiangolo.com/) - 现代Web框架
- [pydub](https://github.com/jiaaro/pydub) - 音频处理库

## 📞 联系方式

- 项目链接: [https://github.com/Acclerate/video-transcriber](https://github.com/Acclerate/video-transcriber)
- 问题反馈: [Issues](https://github.com/Acclerate/video-transcriber/issues)

---

**如果这个项目对你有帮助，请给个 ⭐ Star 支持一下！**
