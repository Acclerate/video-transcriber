# 视频转文本系统 - 技术设计文档

## 1. 项目概述

### 1.1 功能描述
实现本地视频/音频文件的自动转录，将视频或音频中的语音内容转换为文本。

### 1.2 核心特性
- ✅ 支持多种视频和音频格式上传
- ✅ 高精度语音识别（基于阿里 SenseVoice 模型）
- ✅ 本地处理，保护隐私
- ✅ 中文优化，支持多语言混合识别
- ✅ 提供 Web API 和 CLI 使用方式
- ✅ 支持批量处理
- ✅ 长音频自动分块处理，避免 CUDA OOM
- ✅ 多种输出格式（JSON/TXT/SRT/VTT/char_json/volc_json）

## 2. 技术架构

### 2.1 整体架构
```
┌─────────────────┐    ┌─────────────────┐
│   前端界面      │    │   Web API       │
│   (HTML+JS+CSS) │    │   (FastAPI)     │
└─────────────────┘    └─────────────────┘
         │                       │
         └───────────────────────┼───────────────────────┐
                                 │                       │
                    ┌─────────────────┐    ┌─────────────────┐
                    │   核心处理引擎   │    │   命令行工具    │
                    │   (Core Engine)  │    │   (CLI/Click)   │
                    └─────────────────┘    └─────────────────┘
                                 │
    ┌────────────┬───────────────┼────────────────┬────────────┐
    │            │               │                │            │
┌───▼───┐  ┌───▼───┐     ┌───▼───┐       ┌───▼───┐  ┌───▼───┐
│文件上传│  │文件验证│     │音频提取│       │语音转录│  │结果处理│
│Upload │  │Validate│     │Extract│       │SenseVoice│  │Format │
└───────┘  └───────┘     └───────┘       └───────┘  └───────┘
```

### 2.2 技术栈选型

#### 后端技术栈
- **编程语言**: Python 3.10+
- **Web框架**: FastAPI + Uvicorn
- **音频处理**: FFmpeg + pydub + librosa
- **语音识别**: Alibaba SenseVoice (FunASR + ModelScope + PyTorch)
- **异步处理**: asyncio
- **数据校验**: Pydantic v2 + pydantic-settings
- **CLI**: Click + Rich
- **日志系统**: loguru
- **HTTP客户端**: httpx

#### 前端技术栈
- **基础技术**: HTML5 + CSS3 + JavaScript

#### 系统依赖
- **FFmpeg**: 音视频处理
- **CUDA** (可选): GPU 加速 SenseVoice 推理

## 3. 模块设计

### 3.1 文件上传模块 (services/file_service.py)
```python
class FileService:
    """文件服务"""

    async def validate_file(self, file_path: str) -> tuple[bool, Optional[str]]:
        """验证文件"""

    def get_file_info(self, file_path: str) -> dict:
        """获取文件信息"""
```

**支持视频格式**: MP4, AVI, MKV, MOV, WMV, FLV, WebM, M4V, MPEG

**支持音频格式**: MP3, WAV, M4A, AAC, FLAC, OGG, WMA

### 3.2 音频提取模块 (core/downloader.py)
```python
class AudioExtractor:
    """音频提取器"""

    async def extract_audio(self, video_path: str) -> str:
        """从视频中提取音频"""

    def optimize_audio(self, audio_path: str) -> str:
        """音频预处理优化"""
```

**功能特性**:
- 自动音频提取
- 音频格式转换 (16kHz 单声道 WAV)
- 音量标准化
- 智能音频分块 (utils/audio/chunking.py)

### 3.3 语音转录模块 (core/sensevoice_transcriber.py)
```python
class SenseVoiceTranscriber:
    """SenseVoice 语音转录器"""

    def load_model(self):
        """加载 SenseVoice 模型 (从 ModelScope)"""

    async def transcribe_audio(self, audio_path: str, options: ProcessOptions) -> TranscriptionResult:
        """转录音频为文本"""
```

**SenseVoice 模型**:
- **sensevoice-small**: 244MB, 支持中文、英语、日语、韩语、粤语等多种语言，中文优化

### 3.4 核心引擎 (core/engine.py)
```python
class VideoTranscriptionEngine:
    """视频转录核心引擎"""

    async def process_file(self, file_path: str, options: ProcessOptions) -> TranscriptionResult:
        """处理本地视频/音频文件"""

    async def process_batch(self, file_paths: List[str], options: ProcessOptions) -> BatchResult:
        """批量处理"""
```

### 3.5 服务层
```python
class TranscriptionService:
    """转录服务 — 高层 API，组合所有核心组件"""

class TaskService:
    """任务管理服务 — 状态跟踪、超时处理"""

class FileService:
    """文件服务 — 验证、信息获取"""
```

## 4. 数据模型

### 4.1 请求数据模型
```python
class ProcessOptions(BaseModel):
    """处理选项"""
    model: TranscriptionModel = TranscriptionModel.SENSEVOICE_SMALL
    language: Language = Language.CHINESE
    timestamp_mode: TimestampMode = TimestampMode.OFF
    output_format: OutputFormat = OutputFormat.TXT
    enable_gpu: Optional[bool] = None
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
    model: TranscriptionModel
    paragraphs: List[Paragraph]
    char_timestamps: List[CharTimestamp]

class APIResponse(BaseModel):
    """统一 API 响应"""
    code: int
    message: str
    data: Optional[Any] = None
    timestamp: datetime
```

### 4.3 枚举模型
```python
class TranscriptionModel(str, Enum):
    SENSEVOICE_SMALL = "sensevoice-small"

class Language(str, Enum):
    AUTO = "auto"
    CHINESE = "zh"
    ENGLISH = "en"
    JAPANESE = "ja"
    KOREAN = "ko"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    RUSSIAN = "ru"

class OutputFormat(str, Enum):
    JSON = "json"
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"
    CHAR_JSON = "char_json"
    VOLC_JSON = "volc_json"

class TaskStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
```

## 5. API 接口设计

### 5.1 文件上传转录
```
POST /api/v1/transcribe/file
Content-Type: multipart/form-data

参数:
- files: 视频/音频文件
- model: 模型名称 (sensevoice-small)
- language: 目标语言 (zh)
- format: 输出格式 (txt)
- timestamps: 是否包含时间戳 (false)

响应:
{
    "code": 200,
    "message": "转录成功",
    "data": {
        "task_id": "xxx",
        "video_info": {...},
        "transcription": {...}
    },
    "timestamp": "2025-01-01T00:00:00"
}
```

### 5.2 批量转录
```
POST /api/v1/transcribe/batch
Content-Type: multipart/form-data

参数:
- files: 视频/音频文件列表 (最多20个)
- model: 模型名称
- language: 目标语言
- max_concurrent: 最大并发数 (2)

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
GET /api/v1/transcribe/task/{task_id}

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

### 5.4 其他端点

| 端点 | 方法 | 描述 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/ping` | GET | 心跳检测 |
| `/api/v1/models` | GET | 获取可用模型 |
| `/api/v1/transcribe/tasks` | GET | 列出最近任务 |
| `/api/v1/transcribe/stats` | GET | 获取统计信息 |
| `/api/v1/transcribe/task/{task_id}/cancel` | POST | 取消任务 |
| `/ws/transcribe` | WS | WebSocket 实时转录 |

## 6. 使用示例

### 6.1 Python API 调用
```python
import requests

# 上传文件转录
with open("video.mp4", "rb") as f:
    response = requests.post(
        "http://localhost:8665/api/v1/transcribe/file",
        files={"files": f},
        data={"model": "sensevoice-small", "language": "zh"}
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
    "http://localhost:8665/api/v1/transcribe/batch",
    files=files,
    data={"max_concurrent": 2, "model": "sensevoice-small"}
)
```

### 6.3 命令行工具（CLI）

CLI 是与 Web API 并行的完整使用方式，入口为 `webmain.py`，基于 Click 框架实现命令定义、Rich 库实现终端美化输出。

#### 6.3.1 默认行为

不带任何参数直接运行时，自动启动 Web 服务（等价于 `python webmain.py serve`）：

```python
# webmain.py:588-590
if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append('serve')
    cli()
```

#### 6.3.2 全局选项

所有子命令共享以下全局选项（定义在 `cli` 组上，`webmain.py:129-151`）：

```
python webmain.py [全局选项] <子命令> [子命令选项]
```

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--debug` | 标志 | 否 | 启用调试模式，日志级别强制为 DEBUG，不写日志文件 |
| `--log-level` | 字符串 | `INFO` | 日志级别 (DEBUG/INFO/WARNING/ERROR) |
| `--skip-deps-check` | 标志 | 否 | 跳过启动时的 FFmpeg 依赖检查 |

启动流程：设置日志 → 依赖检查（FFmpeg）→ 进入子命令。若依赖缺失会打印安装指引并退出。

#### 6.3.3 `transcribe` — 单文件转录

转录单个视频或音频文件，是最核心的 CLI 命令。

```
python webmain.py transcribe <file_path> [选项]
```

**参数与选项** (`webmain.py:154-173`)：

| 参数/选项 | 短写 | 类型 | 默认值 | 说明 |
|-----------|------|------|--------|------|
| `file_path` | — | 位置参数（必须） | — | 视频/音频文件路径，Click 自动验证文件存在性 |
| `--model` | `-m` | 选择 | `sensevoice-small` | 语音识别模型 |
| `--language` | `-l` | 选择 | `auto` | 目标语言：auto/zh/en/ja/ko/es/fr/de/ru |
| `--output` | `-o` | 字符串 | 无（控制台输出） | 输出文件路径，自动创建父目录 |
| `--format` | `-f` | 选择 | `txt` | 输出格式：json/txt/srt/vtt/char_json/volc_json |
| `--timestamps` | — | 标志 | 否 | 包含时间戳（已弃用，建议用 `--timestamp-mode`） |
| `--timestamp-mode` | — | 选择 | `none` | 时间戳模式：none=无, sentence=句级, char=逐字 |
| `--quiet` | `-q` | 标志 | 否 | 静默模式，只输出纯文本结果，无进度条和统计 |

**处理流程** (`_transcribe_single`, `webmain.py:176-269`)：

```
输入文件 → 构造 ProcessOptions → TranscriptionService.transcribe_file()
                                                    ↓
                                            核心处理管线：
                                            音频提取(FFmpeg) → 分块(长音频) → SenseVoice ASR → 标点添加 → 段落格式化
                                                    ↓
                                            格式化输出(json/txt/srt/vtt...)
                                                    ↓
                                     -o 指定路径 → 写入文件
                                     无 -o       → 控制台展示(Rich Panel)
```

关键代码路径：
1. **选项构造**（L200-208）：将 CLI 参数映射为 `ProcessOptions` 对象，`enable_gpu` 和 `temperature` 从 `config/settings.py` 全局配置读取
2. **服务调用**（L222-226）：`TranscriptionService.transcribe_file()` — 与 Web API 共享同一入口
3. **进度展示**（L214-219）：用 Rich `Progress` 组件显示进度条，通过 `ProgressCallback` 类（L80-92）桥接服务层回调
4. **输出格式化**（L229-233）：`json` 格式调用 `result.model_dump_json()`，其他格式调用 `utils/output_formatter.format_output()`
5. **统计展示**（L254-262）：置信度、检测语言、处理时间、模型、文本长度

**使用示例**：

```bash
# 基础用法 — 转录视频，纯文本输出到控制台
python webmain.py transcribe video.mp4

# 转录音频文件，输出为 JSON
python webmain.py transcribe recording.m4a -f json -o result.json

# 指定中文，SRT 字幕格式
python webmain.py transcribe video.mp4 -l zh -f srt -o output.srt

# 带句级时间戳
python webmain.py transcribe video.mp4 --timestamp-mode sentence -f json

# 静默模式（适合脚本调用，只输出结果文本）
python webmain.py transcribe video.mp4 -q -f txt

# 输出逐字时间戳的 JSON
python webmain.py transcribe podcast.mp3 --timestamp-mode char -f char_json -o timestamps.json
```

#### 6.3.4 `batch` — 批量转录

从一个文本文件中读取多个文件路径，批量执行转录。

```
python webmain.py batch <file_list> [选项]
```

**参数与选项** (`webmain.py:272-288`)：

| 参数/选项 | 短写 | 类型 | 默认值 | 说明 |
|-----------|------|------|--------|------|
| `file_path` | — | 位置参数（必须） | — | 文件列表路径（每行一个视频/音频路径） |
| `--model` | `-m` | 选择 | `sensevoice-small` | 语音识别模型 |
| `--language` | `-l` | 选择 | `auto` | 目标语言 |
| `--output-dir` | `-d` | 字符串 | `./output` | 输出目录，自动创建 |
| `--format` | `-f` | 选择 | `txt` | 输出格式 |
| `--max-concurrent` | `-c` | 整数 | `3` | 最大并发转录数 |
| `--quiet` | `-q` | 标志 | 否 | 静默模式 |

**处理流程** (`_transcribe_batch`, `webmain.py:291-392`)：

```
读取文件列表 → 跳过空行和注释行(#开头) → 验证每个路径是否存在
                            ↓
              TranscriptionService.transcribe_batch(max_concurrent)
                            ↓
              遍历所有已完成任务 → 格式化结果 → 保存到输出目录
              文件名格式: {原始文件名}_{task_id后8位}.{format}
```

文件列表格式：
```
# 这是注释行
/path/to/video1.mp4
/path/to/recording.m4a
/path/to/podcast.mp3
```

**使用示例**：

```bash
# 批量转录，输出 JSON 到指定目录
python webmain.py batch file_list.txt -f json -d ./results

# 限制并发数为 2（适合 GPU 显存有限的场景）
python webmain.py batch file_list.txt -c 2

# 批量生成 SRT 字幕
python webmain.py batch file_list.txt -f srt -d ./subtitles
```

#### 6.3.5 `serve` — 启动 Web API 服务

```
python webmain.py serve [选项]
```

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--host` | 字符串 | `127.0.0.1` | 监听地址 |
| `--port` | 整数 | `8665` | 监听端口 |
| `--reload` | 标志 | 否 | 开发模式，代码变更自动重载 |

内部通过 `uvicorn.run("api.apimain:app", ...)` 启动 FastAPI 应用（`webmain.py:509-515`）。

```bash
# 默认启动（127.0.0.1:8665）
python webmain.py serve

# 对外开放 + 开发热重载
python webmain.py serve --host 0.0.0.0 --port 8665 --reload
```

#### 6.3.6 `download-model` — 预下载模型

首次使用前或离线环境中，提前下载 SenseVoice 模型到本地缓存。

```
python webmain.py download-model [model] [选项]
```

| 参数/选项 | 类型 | 默认值 | 说明 |
|-----------|------|--------|------|
| `model` | 位置参数 | `sensevoice-small` | 模型名称 |
| `--source` | 选择 | `modelscope` | 下载源 |

内部调用 `utils/model_downloader.download_model()`（`webmain.py:555-560`），模型缓存到 `MODEL_CACHE_DIR` 配置的目录。

```bash
python webmain.py download-model sensevoice-small
```

#### 6.3.7 `check` — 系统依赖检查

检查 FFmpeg 等必需依赖是否安装，显示版本信息。

```bash
python webmain.py check
```

内部调用 `utils.ffmpeg.check_ffmpeg_installed()` 和 `print_dependency_check()`（`webmain.py:468-494`）。

#### 6.3.8 `info` — 系统信息

显示 Python 版本、PyTorch 版本、CUDA 状态、GPU 信息、模型配置和使用统计。

```bash
python webmain.py info
```

内部创建 `SenseVoiceTranscriber` 临时实例获取模型信息（`webmain.py:412-415`），通过 `TranscriptionService.get_statistics()` 获取累计处理统计。

#### 6.3.9 `models` — 查看可用模型

以表格形式展示所有支持的语音识别模型及其参数。

```bash
python webmain.py models
```

#### 6.3.10 `cleanup` — 清理临时文件

清理过期任务记录和临时文件。

```
python webmain.py cleanup [--hours N]
```

| 选项 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--hours` | 整数 | `24` | 清理多少小时前的记录 |

内部调用 `TaskService.cleanup_old_tasks()` 和 `TranscriptionService.cleanup_temp_files()`（`webmain.py:455-459`）。

```bash
# 清理 24 小时前的记录
python webmain.py cleanup

# 清理 7 天前的记录
python webmain.py cleanup --hours 168
```

#### 6.3.11 CLI 与 Web API 的共享架构

CLI 和 Web API 使用完全相同的服务层和核心引擎，区别仅在展示层：

```
CLI (webmain.py)                    Web API (api/apimain.py)
    │                                       │
    ├─ Click 参数解析                        ├─ FastAPI 路由解析
    ├─ Rich 进度条展示                       ├─ WebSocket 进度推送
    │                                       │
    └──────────┬────────────────────────────┘
               ↓
    TranscriptionService (services/transcription_service.py)
               ↓
    VideoTranscriptionEngine (core/engine.py)
               ↓
    AudioExtractor → AudioChunking → SenseVoiceTranscriber
    (core/downloader.py)  (utils/audio/)  (core/sensevoice_transcriber.py)
```

核心共享点：
- **`TranscriptionService`**：CLI 的 `transcribe`/`batch` 和 Web API 的 `/api/v1/transcribe/*` 路由都通过此服务调用
- **`ProcessOptions`**：CLI 参数映射为此对象，Web API 表单参数同样映射为此对象
- **`progress_callback`**：CLI 用 Rich Progress 包装，Web API 用 WebSocket 推送，接口签名一致

## 7. 性能优化

### 7.1 GPU 加速
```python
# 自动检测 CUDA
import torch
if torch.cuda.is_available():
    device = "cuda"
else:
    device = "cpu"
```

### 7.2 音频分块处理
- 长音频自动分段处理（默认超过10分钟启用）
- 每块默认5分钟（300秒），适配8GB显存
- 块之间2秒重叠，避免切断语音
- 超长音频自动切换到 CPU 模式

### 7.3 并发处理
- 使用 Semaphore 控制并发数
- 默认最大 3 个并发任务
- 可根据 GPU 内存调整

### 7.4 内存管理
- 及时清理临时文件
- 定期释放 CUDA 缓存
- 任务完成后清理资源

## 8. 部署说明

### 8.1 环境要求
- Python 3.10+（推荐 3.12）
- FFmpeg
- CUDA (可选，用于 GPU 加速)

### 8.2 启动服务
```bash
# 安装依赖
pip install -r requirements.txt

# 下载模型
python webmain.py download-model sensevoice-small

# 启动 API 服务
python webmain.py serve

# 或使用 uvicorn
uvicorn api.apimain:app --host 0.0.0.0 --port 8665 --reload
```

### 8.3 Docker 部署
```bash
# 构建镜像
docker build -f docker/Dockerfile -t video-transcriber .

# 运行容器
docker run --gpus all -p 8665:8665 -v $(pwd)/temp:/app/temp video-transcriber

# 或使用 Docker Compose
docker-compose -f docker/docker-compose.yml up -d
```
