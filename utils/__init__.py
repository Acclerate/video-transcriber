"""
Video Transcriber 工具模块包
重组后的工具模块，按功能分类
"""

# ============================================================
# 日志工具
# ============================================================
from .logging import (
    LoggerConfig, setup_default_logger, get_logger, init_logger_from_env,
    log_debug, log_info, log_warning, log_error, log_critical, log_exception,
    log_execution, TemporaryLogLevel
)

# ============================================================
# FFmpeg 工具
# ============================================================
from .ffmpeg import (
    check_ffmpeg_installed, get_ffmpeg_version,
    get_ffmpeg_install_command, get_ffmpeg_help_message
)

# ============================================================
# 文件工具
# ============================================================
from .file import (
    format_duration, format_file_size, clean_filename,
    get_file_hash, async_get_file_hash, get_mime_type,
    is_audio_file, is_video_file, ensure_directory,
    get_temp_filename, get_unique_filepath
)

# ============================================================
# 通用工具
# ============================================================
from .common import (
    validate_url, extract_domain, parse_query_params,
    truncate_text, extract_numbers, normalize_text,
    time_ago, retry_on_exception, RateLimiter, batch_items
)

__version__ = "2.0.0"

__all__ = [
    # 日志工具
    "LoggerConfig", "setup_default_logger", "get_logger", "init_logger_from_env",
    "log_debug", "log_info", "log_warning", "log_error", "log_critical", "log_exception",
    "log_execution", "TemporaryLogLevel",

    # FFmpeg 工具
    "check_ffmpeg_installed", "get_ffmpeg_version", "get_ffmpeg_install_command",
    "get_ffmpeg_help_message",

    # 文件工具
    "format_duration", "format_file_size", "clean_filename",
    "get_file_hash", "async_get_file_hash", "get_mime_type",
    "is_audio_file", "is_video_file", "ensure_directory",
    "get_temp_filename", "get_unique_filepath",

    # 通用工具
    "validate_url", "extract_domain", "parse_query_params",
    "truncate_text", "extract_numbers", "normalize_text",
    "time_ago", "retry_on_exception", "RateLimiter", "batch_items",
]
