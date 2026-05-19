"""
测试配置和公共夹具
"""

import os
import tempfile
import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock
from typing import Generator

os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")

# 添加项目根目录到Python路径
import sys
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from models.schemas import (
    TranscriptionResult, TranscriptionSegment,
    TranscriptionModel, Language, TaskStatus, MediaFileInfo, MediaFormat,
    CharTimestamp, Paragraph, OutputFormat
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
        whisper_model=TranscriptionModel.SENSEVOICE_SMALL
    )


@pytest.fixture
def sample_video_info() -> MediaFileInfo:
    """示例媒体文件信息"""
    return MediaFileInfo.model_construct(
        file_path="/path/to/video.mp4",
        file_name="video.mp4",
        file_size=1024000,
        duration=60.0,
        format=MediaFormat.MP4,
    )


@pytest.fixture
def mock_speech_transcriber():
    """模拟 SenseVoice 转录器"""
    transcriber = Mock()
    transcriber.model_name = TranscriptionModel.SENSEVOICE_SMALL
    transcriber.device = "cpu"
    transcriber.load_model = AsyncMock()
    transcriber.transcribe_audio = AsyncMock()
    transcriber.unload_model = AsyncMock()
    transcriber.get_model_info = Mock(return_value={
        "name": "sensevoice-small",
        "device": "cpu",
        "loaded": True
    })
    return transcriber


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
def api_client():
    """API客户端夹具"""
    from fastapi.testclient import TestClient
    from api.apimain import app

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


# 测试标记装饰器
requires_network = pytest.mark.network
requires_gpu = pytest.mark.gpu
slow_test = pytest.mark.slow


@pytest.fixture
def sample_char_timestamps() -> list[CharTimestamp]:
    """示例逐字时间戳"""
    return [
        CharTimestamp(word="你", start=0.0, end=0.3),
        CharTimestamp(word="好", start=0.3, end=0.6),
        CharTimestamp(word="世", start=0.6, end=0.9),
        CharTimestamp(word="界", start=0.9, end=1.2),
    ]


@pytest.fixture
def sample_result_with_char_timestamps(sample_char_timestamps) -> TranscriptionResult:
    """带逐字时间戳的转录结果"""
    seg = TranscriptionSegment(
        start_time=0.0, end_time=1.2,
        text="你好世界", confidence=0.95,
        char_timestamps=sample_char_timestamps,
    )
    return TranscriptionResult(
        text="你好世界",
        language="zh",
        confidence=0.95,
        segments=[seg],
        processing_time=1.0,
        whisper_model=TranscriptionModel.SENSEVOICE_SMALL,
        char_timestamps=sample_char_timestamps,
    )


@pytest.fixture
def sample_result_with_paragraphs() -> TranscriptionResult:
    """带段落的转录结果"""
    paragraphs = [
        Paragraph(index=1, text="这是第一段文字。", start_time=0.0, end_time=5.0, segments=[]),
        Paragraph(index=2, text="这是第二段文字。", start_time=5.5, end_time=10.0, segments=[]),
    ]
    return TranscriptionResult(
        text="这是第一段文字。这是第二段文字。",
        language="zh",
        confidence=0.95,
        segments=[
            TranscriptionSegment(start_time=0.0, end_time=5.0, text="这是第一段文字。", confidence=0.95),
            TranscriptionSegment(start_time=5.5, end_time=10.0, text="这是第二段文字。", confidence=0.95),
        ],
        processing_time=2.0,
        whisper_model=TranscriptionModel.SENSEVOICE_SMALL,
        paragraphs=paragraphs,
    )


def assert_transcription_result_valid(result: TranscriptionResult):
    """验证转录结果对象"""
    assert result.text
    assert result.language
    assert 0 <= result.confidence <= 1
    assert result.processing_time > 0
    assert result.whisper_model in TranscriptionModel

    for segment in result.segments:
        assert segment.start_time >= 0
        assert segment.end_time > segment.start_time
        assert segment.text
        assert 0 <= segment.confidence <= 1
