"""
Video Transcriber 核心模块包
"""

from .downloader import audio_extractor, extract_audio_from_video
from .sensevoice_transcriber import create_sensevoice_transcriber, SenseVoiceTranscriber
from .engine import transcription_engine, transcribe_video_file

__version__ = "1.0.0"

__all__ = [
    # 音频提取器
    "audio_extractor", "extract_audio_from_video",

    # SenseVoice 转录器
    "create_sensevoice_transcriber", "SenseVoiceTranscriber",

    # 引擎
    "transcription_engine", "transcribe_video_file"
]
