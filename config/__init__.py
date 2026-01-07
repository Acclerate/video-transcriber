"""
配置模块
集中管理应用配置
"""

from .settings import settings, Settings
from .constants import (
    # 支持的视频格式
    SUPPORTED_VIDEO_FORMATS,
    SUPPORTED_AUDIO_FORMATS,
    # Whisper 模型信息
    WHISPER_MODELS,
    # 支持的语言
    SUPPORTED_LANGUAGES,
    # 输出格式
    OUTPUT_FORMATS,
    # 文件大小限制
    MAX_FILE_SIZE_MB,
    DEFAULT_CHUNK_SIZE,
    # 超时设置
    DEFAULT_TIMEOUT,
    CLEANUP_INTERVAL,
)

__all__ = [
    "settings",
    "Settings",
    "SUPPORTED_VIDEO_FORMATS",
    "SUPPORTED_AUDIO_FORMATS",
    "WHISPER_MODELS",
    "SUPPORTED_LANGUAGES",
    "OUTPUT_FORMATS",
    "MAX_FILE_SIZE_MB",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_TIMEOUT",
    "CLEANUP_INTERVAL",
]
