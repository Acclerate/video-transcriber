"""
Video Transcriber 数据模型定义
包含所有核心数据结构和Pydantic模型
"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import List, Optional, Dict, Any
import os
from pydantic import BaseModel, Field, validator


class TaskStatus(str, Enum):
    """任务处理状态"""
    PENDING = "pending"
    EXTRACTING = "extracting"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TranscriptionModel(str, Enum):
    """语音识别模型类型"""
    SENSEVOICE_SMALL = "sensevoice-small"  # SenseVoice多语言模型，中文优化


class OutputFormat(str, Enum):
    """输出格式"""
    JSON = "json"
    TXT = "txt"
    SRT = "srt"
    VTT = "vtt"


class Language(str, Enum):
    """支持的语言"""
    AUTO = "auto"
    CHINESE = "zh"
    ENGLISH = "en"
    JAPANESE = "ja"
    KOREAN = "ko"
    SPANISH = "es"
    FRENCH = "fr"
    GERMAN = "de"
    RUSSIAN = "ru"


class VideoFormat(str, Enum):
    """支持的视频格式"""
    MP4 = "mp4"
    AVI = "avi"
    MKV = "mkv"
    MOV = "mov"
    WMV = "wmv"
    FLV = "flv"
    WEBM = "webm"
    MPEG = "mpeg"
    M4V = "m4v"


# =============================================================================
# 基础数据模型
# =============================================================================

class VideoFileInfo(BaseModel):
    """视频文件信息"""
    file_path: str = Field(..., description="视频文件路径")
    file_name: str = Field(..., description="文件名")
    file_size: int = Field(..., description="文件大小(字节)")
    duration: Optional[float] = Field(None, description="视频时长(秒)")
    format: VideoFormat = Field(..., description="视频格式")

    @validator('file_path')
    def file_path_must_exist(cls, v):
        # 规范化路径以防止路径遍历攻击
        try:
            normalized_path = Path(v).resolve()
        except Exception:
            raise ValueError(f'无效的文件路径: {v}')

        # 检查路径是否存在
        if not normalized_path.exists():
            raise ValueError(f'文件不存在: {v}')
        if not normalized_path.is_file():
            raise ValueError(f'路径不是文件: {v}')

        # 防止路径遍历攻击：检查规范化后的路径是否仍在允许的目录内
        # 如果是相对路径，确保不越界
        if not Path(v).is_absolute():
            # 相对路径，转换为绝对路径后检查
            abs_path = Path(os.path.abspath(v))
            # 检查是否包含父目录引用
            if '..' in Path(v).parts:
                raise ValueError(f'路径包含非法的父目录引用: {v}')

        # 返回规范化的绝对路径
        return str(normalized_path)

    @validator('format', pre=True)
    def parse_format(cls, v):
        if isinstance(v, str):
            return v.lower()
        return v


class TranscriptionSegment(BaseModel):
    """转录片段"""
    start_time: float = Field(..., description="开始时间(秒)")
    end_time: float = Field(..., description="结束时间(秒)")
    text: str = Field(..., description="文本内容")
    confidence: float = Field(..., ge=0.0, le=1.0, description="置信度")

    @validator('end_time')
    def end_time_must_be_greater_than_start_time(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('end_time must be greater than start_time')
        return v


class TranscriptionResult(BaseModel):
    """转录结果"""
    text: str = Field(..., description="完整转录文本")
    language: str = Field(..., description="检测到的语言")
    confidence: float = Field(..., ge=0.0, le=1.0, description="整体置信度")
    segments: List[TranscriptionSegment] = Field(default=[], description="转录片段列表")
    processing_time: float = Field(..., description="处理时间(秒)")
    whisper_model: WhisperModel = Field(..., description="使用的模型")

    model_config = {"protected_namespaces": ()}

    @property
    def duration(self) -> float:
        """计算转录总时长"""
        if not self.segments:
            return 0.0
        return max(segment.end_time for segment in self.segments)


# =============================================================================
# 请求/响应模型
# =============================================================================

class ProcessOptions(BaseModel):
    """处理选项"""
    model: WhisperModel = Field(WhisperModel.SMALL, description="Whisper模型")
    language: Language = Field(Language.AUTO, description="目标语言")
    with_timestamps: bool = Field(False, description="是否包含时间戳")
    output_format: OutputFormat = Field(OutputFormat.JSON, description="输出格式")
    enable_gpu: Optional[bool] = Field(None, description="是否启用GPU")
    temperature: float = Field(0.0, ge=0.0, le=1.0, description="采样温度")

    class Config:
        use_enum_values = True


class TranscribeRequest(BaseModel):
    """转录请求"""
    file_path: str = Field(..., description="视频文件路径")
    options: ProcessOptions = Field(
        default=ProcessOptions(
            model=WhisperModel.SMALL,
            language=Language.AUTO,
            with_timestamps=False,
            output_format=OutputFormat.JSON,
            enable_gpu=None,
            temperature=0.0
        ),
        description="处理选项"
    )


class BatchTranscribeRequest(BaseModel):
    """批量转录请求"""
    file_paths: List[str] = Field(..., min_length=1, max_length=20, description="视频文件路径列表")
    options: ProcessOptions = Field(
        default=ProcessOptions(
            model=WhisperModel.SMALL,
            language=Language.AUTO,
            with_timestamps=False,
            output_format=OutputFormat.JSON,
            enable_gpu=None,
            temperature=0.0
        ),
        description="处理选项"
    )
    max_concurrent: int = Field(3, ge=1, le=10, description="最大并发数")


class TaskInfo(BaseModel):
    """任务信息"""
    task_id: str = Field(..., description="任务ID")
    file_path: str = Field(..., description="视频文件路径")
    status: TaskStatus = Field(..., description="任务状态")
    progress: int = Field(0, ge=0, le=100, description="进度百分比")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    started_at: Optional[datetime] = Field(None, description="开始时间")
    completed_at: Optional[datetime] = Field(None, description="完成时间")
    error_message: Optional[str] = Field(None, description="错误信息")
    video_info: Optional[VideoFileInfo] = Field(None, description="视频信息")
    result: Optional[TranscriptionResult] = Field(None, description="转录结果")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class BatchTaskInfo(BaseModel):
    """批量任务信息"""
    batch_id: str = Field(..., description="批次ID")
    total_count: int = Field(..., description="总任务数")
    completed_count: int = Field(0, description="已完成数")
    failed_count: int = Field(0, description="失败数")
    pending_count: int = Field(..., description="待处理数")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    tasks: List[TaskInfo] = Field(default=[], description="任务列表")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# =============================================================================
# API响应模型
# =============================================================================

class APIResponse(BaseModel):
    """API统一响应格式"""
    code: int = Field(..., description="响应码")
    message: str = Field(..., description="响应消息")
    data: Optional[Any] = Field(None, description="响应数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class TranscribeResponse(APIResponse):
    """转录响应"""
    data: Dict[str, Any] = Field(..., description="转录结果数据")


class BatchTranscribeResponse(APIResponse):
    """批量转录响应"""
    data: BatchTaskInfo = Field(..., description="批量任务信息")


class TaskStatusResponse(APIResponse):
    """任务状态响应"""
    data: TaskInfo = Field(..., description="任务信息")


# =============================================================================
# WebSocket消息模型
# =============================================================================

class WSMessageType(str, Enum):
    """WebSocket消息类型"""
    PROGRESS = "progress"
    RESULT = "result"
    ERROR = "error"
    PING = "ping"
    PONG = "pong"


class WSMessage(BaseModel):
    """WebSocket消息"""
    type: WSMessageType = Field(..., description="消息类型")
    data: Dict[str, Any] = Field(..., description="消息数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class WSProgressMessage(WSMessage):
    """WebSocket进度消息"""
    type: WSMessageType = Field(WSMessageType.PROGRESS, description="消息类型")
    data: Dict[str, Any] = Field(..., description="进度数据")


class WSResultMessage(WSMessage):
    """WebSocket结果消息"""
    type: WSMessageType = Field(WSMessageType.RESULT, description="消息类型")
    data: Dict[str, Any] = Field(..., description="转录结果")


class WSErrorMessage(WSMessage):
    """WebSocket错误消息"""
    type: WSMessageType = Field(WSMessageType.ERROR, description="消息类型")
    data: Dict[str, str] = Field(..., description="错误信息")


# =============================================================================
# 错误模型
# =============================================================================

class ErrorCode(str, Enum):
    """错误代码"""
    INVALID_FILE_PATH = "INVALID_FILE_PATH"
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    AUDIO_EXTRACT_FAILED = "AUDIO_EXTRACT_FAILED"
    TRANSCRIPTION_FAILED = "TRANSCRIPTION_FAILED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_PARAMETERS = "INVALID_PARAMETERS"
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    MODEL_LOAD_FAILED = "MODEL_LOAD_FAILED"


class ErrorDetail(BaseModel):
    """错误详情"""
    code: ErrorCode = Field(..., description="错误代码")
    message: str = Field(..., description="错误消息")
    details: Optional[Dict[str, Any]] = Field(None, description="错误详细信息")
    timestamp: datetime = Field(default_factory=datetime.now, description="错误时间")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


# =============================================================================
# 配置模型
# =============================================================================

class AppConfig(BaseModel):
    """应用配置"""
    host: str = Field("0.0.0.0", description="服务主机")
    port: int = Field(8665, description="服务端口")
    debug: bool = Field(False, description="调试模式")
    default_model: WhisperModel = Field(WhisperModel.SMALL, description="默认模型")
    enable_gpu: bool = Field(True, description="启用GPU")
    temp_dir: str = Field("./temp", description="临时目录")
    max_file_size: int = Field(500, description="最大文件大小(MB)")
    cleanup_after: int = Field(3600, description="清理间隔(秒)")
    log_level: str = Field("INFO", description="日志级别")
    max_concurrent_tasks: int = Field(3, description="最大并发任务数")

    class Config:
        env_prefix = ""
        case_sensitive = False


# =============================================================================
# 导出所有模型
# =============================================================================

__all__ = [
    # 枚举
    "TaskStatus", "WhisperModel", "OutputFormat", "Language",
    "VideoFormat", "WSMessageType", "ErrorCode",

    # 基础模型
    "VideoFileInfo", "TranscriptionSegment", "TranscriptionResult",

    # 请求模型
    "ProcessOptions", "TranscribeRequest", "BatchTranscribeRequest",

    # 任务模型
    "TaskInfo", "BatchTaskInfo",

    # 响应模型
    "APIResponse", "TranscribeResponse", "BatchTranscribeResponse",
    "TaskStatusResponse",

    # WebSocket模型
    "WSMessage", "WSProgressMessage", "WSResultMessage", "WSErrorMessage",

    # 错误模型
    "ErrorDetail",

    # 配置模型
    "AppConfig"
]
