"""
FFmpeg 工具模块
提供 FFmpeg 检测和辅助功能
"""

from .checker import (
    check_ffmpeg_installed,
    get_ffmpeg_version,
    get_ffmpeg_install_command,
    get_ffmpeg_help_message
)

__all__ = [
    "check_ffmpeg_installed",
    "get_ffmpeg_version",
    "get_ffmpeg_install_command",
    "get_ffmpeg_help_message",
]
