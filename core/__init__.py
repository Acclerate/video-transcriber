"""
Video Transcriber 核心模块包
"""

from .parser import video_parser, parse_video_url, validate_video_url, detect_video_platform
from .downloader import video_downloader, download_video_and_extract_audio  
from .transcriber import speech_transcriber, transcribe_audio_file
from .engine import transcription_engine, transcribe_video_url

__version__ = "1.0.0"

__all__ = [
    # 解析器
    "video_parser", "parse_video_url", "validate_video_url", "detect_video_platform",
    
    # 下载器
    "video_downloader", "download_video_and_extract_audio",
    
    # 转录器
    "speech_transcriber", "transcribe_audio_file",
    
    # 引擎
    "transcription_engine", "transcribe_video_url"
]