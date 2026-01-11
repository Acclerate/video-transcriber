# 视频转文本系统 - 技术设计文档

## 1. 项目概述

### 1.1 功能描述
实现本地视频文件的自动转录，将视频中的语音内容转换为文本。

### 1.2 核心特性
- ✅ 支持多种视频格式上传
- ✅ 高精度语音识别（基于 OpenAI Whisper）
- ✅ 本地处理，保护隐私
- ✅ 支持中英文混合识别
- ✅ 提供 Web API 使用方式
- ✅ 支持批量处理

## 2. 技术架构

### 2.1 整体架构
```
┌─────────────────┐    ┌─────────────────┐
│   前端界面      │    │   Web API       │
│   (HTML+JS)     │    │   (FastAPI)     │
└─────────────────┘    └─────────────────┘
         │                       │
         └───────────────────────┼───────────────────────┐
                                 │                       │
                    ┌─────────────────┐    ┌─────────────────┐
                    │   核心处理引擎   │    │   命令行工具    │
                    │   (Core Engine)  │    │   (CLI)         │
                    └─────────────────┘    └─────────────────┘
                                 │
    ┌────────────┬───────────────┼────────────────┬────────────┐
    │            │               │                │            │
┌───▼───┐  ┌───▼───┐     ┌───▼───┐       ┌───▼───┐  ┌───▼───┐
│文件上传│  │文件验证│     │音频提取│       │语音转录│  │结果处理│
│Upload │  │Validate│     │Extract│       │Whisper│  │Format │
└───────┘  └───────┘     └───────┘       └───────┘  └───────┘
```

### 2.2 技术栈选型

#### 后端技术栈
- **编程语言**: Python 3.8+
- **Web框架**: FastAPI
- **音频处理**: FFmpeg + pydub
- **语音识别**: OpenAI Whisper
- **异步处理**: asyncio
- **日志系统**: loguru

#### 前端技术栈
- **基础技术**: HTML5 + CSS3 + JavaScript
- **UI框架**: Bootstrap 5
- **HTTP请求**: Fetch API

#### 系统依赖
- **FFmpeg**: 音视频处理
- **CUDA** (可选): GPU 加速 Whisper 推理

## 3. 模块设计

### 3.1 文件上传模块
```python
class FileService:
    """文件服务"""

    def validate_file(self, file_path: str) -> tuple[bool, Optional[str]]:
        """验证文件"""

    def get_file_info(self, file_path: str) -> dict:
        """获取文件信息"""
```

**支持格式**: MP4, AVI, MKV, MOV, WMV, FLV, WebM

### 3.2 音频提取模块 (downloader.py)
```python
class AudioExtractor:
    """音频提取器"""

    def extract_audio(self, video_path: str) -> str:
        """从视频中提取音频"""

    def optimize_audio(self, audio_path: str) -> str:
        """音频预处理优化"""
```

**功能特性**:
- 自动音频提取
- 音频格式转换 (16kHz 单声道 WAV)
- 音量标准化
- 静音检测和去除

### 3.3 语音转录模块 (transcriber.py)
```python
class SpeechTranscriber:
    """语音转录器"""

    def load_model(self, model: TranscriptionModel):
        """加载 Whisper 模型"""

    def transcribe_audio(self, audio_path: str) -> TranscriptionResult:
        """转录音频为文本"""

    def format_output(self, result: TranscriptionResult, format: OutputFormat) -> str:
        """格式化输出"""
```

**Whisper模型选择**:
- **tiny**: 39 MB, 快速但准确率较低
- **base**: 74 MB, 平衡速度和准确率
- **small**: 244 MB, 推荐用于大多数场景
- **medium**: 769 MB, 高准确率
- **large**: 1550 MB, 最高准确率

### 3.4 核心引擎 (engine.py)
```python
class VideoTranscriptionEngine:
    """视频转录核心引擎"""

    def process_video_file(self, file_path: str, options: ProcessOptions) -> TranscriptionResult:
        """处理本地视频文件"""

    def process_batch_files(self, file_paths: List[str], options: ProcessOptions) -> BatchResult:
        """批量处理"""
```

## 4. 数据模型

### 4.1 请求数据模型
```python
class ProcessOptions(BaseModel):
    """处理选项"""
    model: TranscriptionModel = TranscriptionModel.SMALL
    language: Language = Language.AUTO
    with_timestamps: bool = False
    output_format: OutputFormat = OutputFormat.TXT
    temperature: float = 0.0
```

### 4.2 响应数据模型
```python
class TranscriptionResult(BaseModel):
    """转录结果"""
    text: str
    language: str
    confidence: float
    segments: List[TranscriptionSegment]
    processing_time: float
    whisper_model: TranscriptionModel
```

### 4.3 任务状态模型
```python
class TaskStatus(str, Enum):
    """任务状态"""
    PENDING = "pending"
    EXTRACTING = "extracting"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"
```

## 5. API 接口设计

### 5.1 文件上传转录
```
POST /api/v1/transcribe
Content-Type: multipart/form-data

参数:
- file: 视频文件
- model: Whisper 模型 (small)
- language: 目标语言 (auto)
- output_format: 输出格式 (txt)
- timestamps: 是否包含时间戳 (false)

响应:
{
    "code": 200,
    "message": "转录成功",
    "data": {
        "video_info": {...},
        "transcription": {...}
    }
}
```

### 5.2 批量转录
```
POST /api/v1/batch-transcribe
Content-Type: multipart/form-data

参数:
- files: 视频文件列表 (最多10个)
- model: Whisper 模型
- language: 目标语言
- max_concurrent: 最大并发数 (3)

响应:
{
    "code": 200,
    "message": "批量任务已创建",
    "data": {
        "batch_id": "xxx",
        "total_files": 5,
        "status": "processing"
    }
}
```

### 5.3 任务状态查询
```
GET /api/v1/status/{task_id}

响应:
{
    "code": 200,
    "message": "查询成功",
    "data": {
        "task_id": "xxx",
        "status": "completed",
        "progress": 100,
        "result": {...}
    }
}
```

## 6. 使用示例

### 6.1 Python API 调用
```python
import requests

# 上传文件转录
with open("video.mp4", "rb") as f:
    response = requests.post(
        "http://localhost:8665/api/v1/transcribe",
        files={"file": f},
        data={"model": "small", "language": "auto"}
    )
    result = response.json()
    print(result["data"]["transcription"]["text"])
```

### 6.2 批量处理
```python
files = [
    ("files", open("video1.mp4", "rb")),
    ("files", open("video2.mp4", "rb")),
    ("files", open("video3.mp4", "rb"))
]

response = requests.post(
    "http://localhost:8665/api/v1/batch-transcribe",
    files=files,
    data={"max_concurrent": 3}
)
```

## 7. 性能优化

### 7.1 GPU 加速
```python
# 自动检测 CUDA
import torch
if torch.cuda.is_available():
    device = "cuda"
else:
    device = "cpu"

# 加载模型到 GPU
model.to(device)
```

### 7.2 并发处理
- 使用 Semaphore 控制并发数
- 默认最大 3 个并发任务
- 可根据 GPU 内存调整

### 7.3 内存管理
- 及时清理临时文件
- 定期释放 CUDA 缓存
- 任务完成后清理资源

## 8. 部署说明

### 8.1 环境要求
- Python 3.8+
- FFmpeg
- CUDA (可选，用于 GPU 加速)

### 8.2 启动服务
```bash
# 安装依赖
pip install -r requirements.txt

# 启动 API 服务
python main.py serve

# 或使用 uvicorn
uvicorn api.main:app --host 0.0.0.0 --port 8665
```

### 8.3 Docker 部署
```bash
# 构建镜像
docker build -f docker/Dockerfile -t video-transcriber .

# 运行容器
docker run -p 8665:8665 video-transcriber
```
