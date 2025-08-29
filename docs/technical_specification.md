# 短视频转文本系统 - 技术设计文档

## 1. 项目概述

### 1.1 功能描述
实现抖音、B站等平台分享链接对应短视频的自动转录，将视频中的语音内容转换为文本。

### 1.2 核心特性
- ✅ 支持抖音、B站等主流短视频平台
- ✅ 高精度语音识别（基于OpenAI Whisper）
- ✅ 本地处理，保护隐私
- ✅ 支持中英文混合识别
- ✅ 提供命令行和Web API两种使用方式
- ✅ 支持批量处理

## 2. 技术架构

### 2.1 整体架构
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   前端界面      │    │   Web API       │    │   命令行工具    │
│   (HTML+JS)     │    │   (FastAPI)     │    │   (CLI)         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   核心处理引擎   │
                    │   (Core Engine)  │
                    └─────────────────┘
                                 │
    ┌────────────┬────────────────┼────────────────┬────────────┐
    │            │                │                │            │
┌───▼───┐  ┌───▼───┐       ┌───▼───┐       ┌───▼───┐  ┌───▼───┐
│链接解析│  │视频下载│       │音频提取│       │语音转录│  │结果处理│
│Parser │  │Download│       │Extract│       │Whisper│  │Format │
└───────┘  └───────┘       └───────┘       └───────┘  └───────┘
```

### 2.2 技术栈选型

#### 后端技术栈
- **编程语言**: Python 3.8+
- **Web框架**: FastAPI
- **视频处理**: yt-dlp + FFmpeg
- **音频处理**: pydub
- **语音识别**: OpenAI Whisper
- **异步处理**: asyncio
- **日志系统**: loguru

#### 前端技术栈
- **基础技术**: HTML5 + CSS3 + JavaScript
- **UI框架**: Bootstrap 5
- **HTTP请求**: Fetch API

#### 系统依赖
- **FFmpeg**: 音视频处理
- **CUDA** (可选): GPU加速Whisper推理

## 3. 模块设计

### 3.1 链接解析模块 (parser.py)
```python
class VideoLinkParser:
    """视频链接解析器"""
    
    def parse_share_link(self, url: str) -> VideoInfo:
        """解析分享链接，获取视频信息"""
        
    def extract_video_id(self, url: str, platform: str) -> str:
        """提取视频ID"""
        
    def get_video_metadata(self, video_id: str, platform: str) -> dict:
        """获取视频元数据"""
```

**支持平台**:
- 抖音 (douyin.com)
- B站 (bilibili.com)
- 快手 (kuaishou.com) - 后期扩展
- 小红书 (xiaohongshu.com) - 后期扩展

### 3.2 视频下载模块 (downloader.py)
```python
class VideoDownloader:
    """视频下载器"""
    
    def download_video(self, video_info: VideoInfo) -> str:
        """下载视频文件"""
        
    def extract_audio(self, video_path: str) -> str:
        """从视频中提取音频"""
        
    def optimize_audio(self, audio_path: str) -> str:
        """音频预处理优化"""
```

**功能特性**:
- 自动选择最优质量
- 支持音频直接提取
- 音频格式转换和优化

### 3.3 语音转录模块 (transcriber.py)
```python
class SpeechTranscriber:
    """语音转录器"""
    
    def transcribe_audio(self, audio_path: str) -> TranscriptionResult:
        """转录音频为文本"""
        
    def transcribe_with_timestamps(self, audio_path: str) -> TimestampedTranscription:
        """带时间戳的转录"""
        
    def batch_transcribe(self, audio_paths: List[str]) -> List[TranscriptionResult]:
        """批量转录"""
```

**Whisper模型选择**:
- **tiny**: 39 MB, 快速但准确率较低
- **base**: 74 MB, 平衡速度和准确率
- **small**: 244 MB, 推荐用于大多数场景
- **medium**: 769 MB, 高准确率
- **large**: 1550 MB, 最高准确率

### 3.4 核心引擎 (core.py)
```python
class VideoTranscriptionEngine:
    """视频转录核心引擎"""
    
    def process_video_link(self, url: str, options: ProcessOptions) -> TranscriptionResult:
        """处理视频链接的主流程"""
        
    def process_batch(self, urls: List[str], options: ProcessOptions) -> List[TranscriptionResult]:
        """批量处理"""
```

## 4. 数据模型

### 4.1 核心数据结构
```python
@dataclass
class VideoInfo:
    """视频信息"""
    video_id: str
    title: str
    platform: str
    duration: int
    url: str
    thumbnail: str

@dataclass
class TranscriptionResult:
    """转录结果"""
    text: str
    confidence: float
    language: str
    segments: List[TranscriptionSegment]
    processing_time: float

@dataclass
class TranscriptionSegment:
    """转录片段"""
    start_time: float
    end_time: float
    text: str
    confidence: float
```

## 5. API接口设计

### 5.1 RESTful API

#### 单个视频转录
```http
POST /api/v1/transcribe
Content-Type: application/json

{
    "url": "https://v.douyin.com/xxxxx",
    "options": {
        "model": "small",
        "language": "auto",
        "with_timestamps": true
    }
}
```

#### 批量视频转录
```http
POST /api/v1/batch-transcribe
Content-Type: application/json

{
    "urls": ["url1", "url2", "url3"],
    "options": {
        "model": "small",
        "language": "auto"
    }
}
```

#### 查询处理状态
```http
GET /api/v1/status/{task_id}
```

### 5.2 WebSocket API (实时进度)
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/transcribe');
ws.send(JSON.stringify({
    'url': 'https://v.douyin.com/xxxxx',
    'options': {'model': 'small'}
}));
```

## 6. 性能优化

### 6.1 处理速度优化
- **GPU加速**: 支持CUDA加速Whisper推理
- **模型缓存**: 预加载Whisper模型避免重复加载
- **异步处理**: 使用asyncio实现并发处理
- **分段处理**: 长音频自动分段处理

### 6.2 存储优化
- **临时文件清理**: 自动清理下载的临时文件
- **音频格式优化**: 转换为最适合识别的格式
- **缓存机制**: 缓存已处理的结果

## 7. 错误处理

### 7.1 常见错误场景
- 链接解析失败
- 视频下载失败
- 音频提取失败
- 语音识别失败
- 网络连接问题

### 7.2 错误处理策略
- 重试机制
- 降级方案
- 详细错误日志
- 用户友好的错误提示

## 8. 安全考虑

### 8.1 输入验证
- URL格式验证
- 文件大小限制
- 请求频率限制

### 8.2 隐私保护
- 本地处理，不上传音频到第三方
- 临时文件加密存储
- 定期清理处理痕迹

## 9. 部署架构

### 9.1 开发环境
```bash
Python 3.8+ + pip + FFmpeg
```

### 9.2 生产环境
```bash
Docker + Nginx + Gunicorn
```

### 9.3 云端部署
- 支持AWS/阿里云/腾讯云
- 容器化部署
- 负载均衡