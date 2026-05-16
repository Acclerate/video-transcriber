"""
Video Transcriber 核心模块包
"""

from .downloader import audio_extractor, extract_audio_from_video
from .sensevoice_transcriber import create_sensevoice_transcriber, SenseVoiceTranscriber

__version__ = "1.0.0"

__all__ = [
    "audio_extractor", "extract_audio_from_video",
    "create_sensevoice_transcriber", "SenseVoiceTranscriber",
]
