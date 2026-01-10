"""
配置模块
集中管理应用配置
"""

from .settings import settings, Settings
from .constants import (
    # Whisper 模型信息
    WHISPER_MODELS,
    # 支持的语言
    SUPPORTED_LANGUAGES,
    # 输出格式
    OUTPUT_FORMATS,
    # 文件大小限制
    DEFAULT_CHUNK_SIZE,
    # 超时设置
    DEFAULT_TIMEOUT,
    CLEANUP_INTERVAL,
)

__all__ = [
    "settings",
    "Settings",
    "WHISPER_MODELS",
    "SUPPORTED_LANGUAGES",
    "OUTPUT_FORMATS",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_TIMEOUT",
    "CLEANUP_INTERVAL",
]
