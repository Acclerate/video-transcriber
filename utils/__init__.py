"""
Video Transcriber 工具模块包
"""

from .logger import (
    LoggerConfig, setup_default_logger, get_logger, init_logger_from_env,
    log_debug, log_info, log_warning, log_error, log_critical, log_exception,
    log_execution, TemporaryLogLevel
)

from .helpers import (
    format_duration, format_file_size, validate_url, extract_domain,
    clean_filename, get_file_hash, async_get_file_hash, get_mime_type,
    is_audio_file, is_video_file, ensure_directory, get_temp_filename,
    parse_query_params, truncate_text, extract_numbers, normalize_text,
    time_ago, retry_on_exception, RateLimiter, batch_items,
    # FFmpeg 检测相关
    check_ffmpeg_installed, get_ffmpeg_version, get_ffmpeg_install_command,
    get_ffmpeg_help_message, check_dependencies, print_dependency_check
)

__version__ = "1.0.0"

__all__ = [
    # 日志工具
    "LoggerConfig", "setup_default_logger", "get_logger", "init_logger_from_env",
    "log_debug", "log_info", "log_warning", "log_error", "log_critical", "log_exception",
    "log_execution", "TemporaryLogLevel",

    # 辅助工具
    "format_duration", "format_file_size", "validate_url", "extract_domain",
    "clean_filename", "get_file_hash", "async_get_file_hash", "get_mime_type",
    "is_audio_file", "is_video_file", "ensure_directory", "get_temp_filename",
    "parse_query_params", "truncate_text", "extract_numbers", "normalize_text",
    "time_ago", "retry_on_exception", "RateLimiter", "batch_items",

    # FFmpeg 检测
    "check_ffmpeg_installed", "get_ffmpeg_version", "get_ffmpeg_install_command",
    "get_ffmpeg_help_message", "check_dependencies", "print_dependency_check"
]