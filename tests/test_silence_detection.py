"""
静音检测测试
测试 core/downloader.py 中 AudioExtractor.detect_silence_ranges() 方法
"""

import pytest
from unittest.mock import patch, MagicMock


def _make_audio_extractor():
    from core.downloader import AudioExtractor
    extractor = AudioExtractor.__new__(AudioExtractor)
    return extractor


class TestDetectSilenceRanges:

    def test_speech_with_silence_gaps(self):
        extractor = _make_audio_extractor()

        with patch("pydub.silence.detect_nonsilent") as mock_detect, \
             patch("pydub.AudioSegment.from_file") as mock_from_file:
            mock_audio = MagicMock()
            mock_audio.__len__ = MagicMock(return_value=10000)
            mock_from_file.return_value = mock_audio
            mock_detect.return_value = [(0, 2000), (4000, 7000), (9000, 10000)]

            result = extractor.detect_silence_ranges("test.wav")

            assert len(result) == 2
            assert result[0] == (2.0, 4.0)
            assert result[1] == (7.0, 9.0)

    def test_no_speech_returns_full_silence(self):
        extractor = _make_audio_extractor()

        with patch("pydub.silence.detect_nonsilent") as mock_detect, \
             patch("pydub.AudioSegment.from_file") as mock_from_file:
            mock_audio = MagicMock()
            mock_audio.__len__ = MagicMock(return_value=5000)
            mock_from_file.return_value = mock_audio
            mock_detect.return_value = []

            result = extractor.detect_silence_ranges("test.wav")

            assert len(result) == 1
            assert result[0] == (0.0, 5.0)

    def test_continuous_speech_no_silence(self):
        extractor = _make_audio_extractor()

        with patch("pydub.silence.detect_nonsilent") as mock_detect, \
             patch("pydub.AudioSegment.from_file") as mock_from_file:
            mock_audio = MagicMock()
            mock_audio.__len__ = MagicMock(return_value=5000)
            mock_from_file.return_value = mock_audio
            mock_detect.return_value = [(0, 5000)]

            result = extractor.detect_silence_ranges("test.wav")

            assert len(result) == 0

    def test_silence_at_start(self):
        extractor = _make_audio_extractor()

        with patch("pydub.silence.detect_nonsilent") as mock_detect, \
             patch("pydub.AudioSegment.from_file") as mock_from_file:
            mock_audio = MagicMock()
            mock_audio.__len__ = MagicMock(return_value=10000)
            mock_from_file.return_value = mock_audio
            mock_detect.return_value = [(2000, 10000)]

            result = extractor.detect_silence_ranges("test.wav")

            assert len(result) == 1
            assert result[0] == (0.0, 2.0)

    def test_short_silence_filtered(self):
        extractor = _make_audio_extractor()

        with patch("pydub.silence.detect_nonsilent") as mock_detect, \
             patch("pydub.AudioSegment.from_file") as mock_from_file:
            mock_audio = MagicMock()
            mock_audio.__len__ = MagicMock(return_value=10000)
            mock_from_file.return_value = mock_audio
            mock_detect.return_value = [(0, 4900), (5100, 10000)]

            result = extractor.detect_silence_ranges("test.wav", min_silence_len=300)

            assert len(result) == 0

    def test_import_error_returns_empty(self):
        extractor = _make_audio_extractor()

        with patch("pydub.AudioSegment.from_file", side_effect=ImportError):
            result = extractor.detect_silence_ranges("test.wav")
            assert result == []

    def test_units_are_seconds(self):
        extractor = _make_audio_extractor()

        with patch("pydub.silence.detect_nonsilent") as mock_detect, \
             patch("pydub.AudioSegment.from_file") as mock_from_file:
            mock_audio = MagicMock()
            mock_audio.__len__ = MagicMock(return_value=60000)
            mock_from_file.return_value = mock_audio
            mock_detect.return_value = [(0, 25000), (30000, 60000)]

            result = extractor.detect_silence_ranges("test.wav")

            assert len(result) == 1
            assert result[0] == (25.0, 30.0)
