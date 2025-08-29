"""
测试配置和公共夹具
"""

import os
import tempfile
import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from typing import Generator, Dict, Any

# 添加项目根目录到Python路径
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.schemas import (
    VideoInfo, TranscriptionResult, TranscriptionSegment,
    Platform, WhisperModel, Language, TaskStatus
)


@pytest.fixture(scope="session")
def event_loop():
    """创建事件循环"""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """临时目录夹具"""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def sample_video_info() -> VideoInfo:
    """示例视频信息"""
    return VideoInfo(
        video_id="test_123456",
        title="测试视频标题",
        platform=Platform.DOUYIN,
        duration=30.5,
        url="https://v.douyin.com/test123",
        thumbnail="https://example.com/thumb.jpg",
        uploader="测试用户",
        upload_date=None,
        view_count=1000,
        description="这是一个测试视频"
    )


@pytest.fixture
def sample_transcription_segments() -> list[TranscriptionSegment]:
    """示例转录片段"""
    return [
        TranscriptionSegment(
            start_time=0.0,
            end_time=5.2,
            text="这是第一段文本",
            confidence=0.95
        ),
        TranscriptionSegment(
            start_time=5.2,
            end_time=10.8,
            text="这是第二段文本",
            confidence=0.92
        ),
        TranscriptionSegment(
            start_time=10.8,
            end_time=15.0,
            text="这是第三段文本",
            confidence=0.88
        )
    ]


@pytest.fixture
def sample_transcription_result(sample_transcription_segments) -> TranscriptionResult:
    """示例转录结果"""
    full_text = " ".join(segment.text for segment in sample_transcription_segments)
    avg_confidence = sum(seg.confidence for seg in sample_transcription_segments) / len(sample_transcription_segments)
    
    return TranscriptionResult(
        text=full_text,
        language="zh",
        confidence=avg_confidence,
        segments=sample_transcription_segments,
        processing_time=12.5,
        whisper_model=WhisperModel.SMALL
    )


@pytest.fixture
def mock_video_parser():
    """模拟视频解析器"""
    parser = Mock()
    parser.detect_platform = Mock(return_value=Platform.DOUYIN)
    parser.validate_url = Mock(return_value=True)
    parser.get_video_info = AsyncMock()
    return parser


@pytest.fixture
def mock_video_downloader():
    """模拟视频下载器"""
    downloader = Mock()
    downloader.download_video = AsyncMock(return_value="/tmp/test_video.mp4")
    downloader.download_audio_only = AsyncMock(return_value="/tmp/test_audio.wav")
    downloader.extract_audio = AsyncMock(return_value="/tmp/test_audio.wav")
    downloader.optimize_audio_for_transcription = AsyncMock(return_value="/tmp/test_audio_optimized.wav")
    downloader.cleanup_files = Mock(return_value=5)
    return downloader


@pytest.fixture
def mock_speech_transcriber():
    """模拟语音转录器"""
    transcriber = Mock()
    transcriber.model_name = WhisperModel.SMALL
    transcriber.device = "cpu"
    transcriber.load_model = AsyncMock()
    transcriber.transcribe_audio = AsyncMock()
    transcriber.format_output = Mock()
    transcriber.get_model_info = Mock(return_value={
        "name": "small",
        "device": "cpu",
        "loaded": True
    })
    return transcriber


@pytest.fixture
def mock_whisper_model():
    """模拟Whisper模型"""
    model = Mock()
    model.transcribe = Mock(return_value={
        "text": "这是测试转录文本",
        "language": "zh",
        "segments": [
            {
                "start": 0.0,
                "end": 5.0,
                "text": "这是测试转录文本",
                "avg_logprob": -0.5
            }
        ]
    })
    return model


@pytest.fixture
def sample_audio_file(temp_dir) -> Path:
    """创建示例音频文件"""
    audio_file = temp_dir / "test_audio.wav"
    # 创建一个空的WAV文件用于测试
    audio_file.write_bytes(b"RIFF\x00\x00\x00\x00WAVEfmt \x00\x00\x00\x00")
    return audio_file


@pytest.fixture
def sample_video_file(temp_dir) -> Path:
    """创建示例视频文件"""
    video_file = temp_dir / "test_video.mp4"
    # 创建一个空的MP4文件用于测试
    video_file.write_bytes(b"\x00\x00\x00\x18ftypmp41")
    return video_file


@pytest.fixture
def test_urls() -> Dict[str, str]:
    """测试用的URL"""
    return {
        "douyin_valid": "https://v.douyin.com/ieFvvPLX/",
        "douyin_invalid": "https://v.douyin.com/invalid",
        "bilibili_valid": "https://www.bilibili.com/video/BV1234567890",
        "bilibili_invalid": "https://www.bilibili.com/video/invalid",
        "unsupported": "https://www.youtube.com/watch?v=test",
        "invalid_url": "not-a-url"
    }


@pytest.fixture
def api_client():
    """API客户端夹具"""
    from fastapi.testclient import TestClient
    from api.main import app
    
    return TestClient(app)


@pytest.fixture
def mock_env_vars(monkeypatch):
    """模拟环境变量"""
    env_vars = {
        "LOG_LEVEL": "DEBUG",
        "TEMP_DIR": "/tmp/test",
        "DEFAULT_MODEL": "tiny",
        "ENABLE_GPU": "false",
        "MAX_FILE_SIZE": "50",
        "CLEANUP_AFTER": "1800"
    }
    
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    
    return env_vars


@pytest.fixture
def mock_ytdl_info() -> Dict[str, Any]:
    """模拟yt-dlp返回的视频信息"""
    return {
        "id": "test_video_123",
        "title": "测试视频标题",
        "duration": 30.5,
        "webpage_url": "https://v.douyin.com/test123",
        "thumbnail": "https://example.com/thumb.jpg",
        "uploader": "测试用户",
        "view_count": 1000,
        "description": "这是一个测试视频",
        "upload_date": "20240829"
    }


# 测试标记装饰器
requires_network = pytest.mark.network
requires_gpu = pytest.mark.gpu
slow_test = pytest.mark.slow


# 测试工具函数
def assert_video_info_valid(video_info: VideoInfo):
    """验证视频信息对象"""
    assert video_info.video_id
    assert video_info.title
    assert video_info.platform in Platform
    assert video_info.duration > 0
    assert video_info.url


def assert_transcription_result_valid(result: TranscriptionResult):
    """验证转录结果对象"""
    assert result.text
    assert result.language
    assert 0 <= result.confidence <= 1
    assert result.processing_time > 0
    assert result.whisper_model in WhisperModel
    
    for segment in result.segments:
        assert segment.start_time >= 0
        assert segment.end_time > segment.start_time
        assert segment.text
        assert 0 <= segment.confidence <= 1