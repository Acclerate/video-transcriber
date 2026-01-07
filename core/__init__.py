"""
Video Transcriber 核心模块包
"""

from .downloader import audio_extractor, extract_audio_from_video
from .transcriber import speech_transcriber, transcribe_audio_file
from .engine import transcription_engine, transcribe_video_file

__version__ = "1.0.0"

__all__ = [
    # 音频提取器
    "audio_extractor", "extract_audio_from_video",

    # 转录器
    "speech_transcriber", "transcribe_audio_file",

    # 引擎
    "transcription_engine", "transcribe_video_file"
]
