"""
输出格式化模块测试
覆盖 utils/output_formatter.py 所有函数
"""

import json
import pytest
import unittest.mock

from models.schemas import (
    TranscriptionResult, TranscriptionSegment, TranscriptionModel,
    CharTimestamp, Paragraph, OutputFormat,
)
from utils.output_formatter import (
    format_output, _format_txt, _format_srt, _format_vtt,
    _format_char_json, _format_volc_json, _strip_subtitle_punct,
    _segment_by_punctuation, _format_srt_time, _format_vtt_time,
)


def _make_segment(start: float, end: float, text: str, confidence: float = 0.95,
                  char_timestamps: list = None) -> TranscriptionSegment:
    return TranscriptionSegment(
        start_time=start, end_time=end, text=text,
        confidence=confidence,
        char_timestamps=char_timestamps or [],
    )


def _make_result(text: str, segments=None, paragraphs=None,
                 char_timestamps=None) -> TranscriptionResult:
    return TranscriptionResult(
        text=text, language="zh", confidence=0.95,
        segments=segments or [],
        processing_time=1.0,
        whisper_model=TranscriptionModel.SENSEVOICE_SMALL,
        paragraphs=paragraphs or [],
        char_timestamps=char_timestamps or [],
    )


# ============================================================
# _format_srt_time / _format_vtt_time
# ============================================================

class TestFormatSrtTime:

    def test_zero(self):
        assert _format_srt_time(0) == "00:00:00,000"

    def test_one_hour_plus(self):
        assert _format_srt_time(3661.5) == "01:01:01,500"

    def test_milliseconds(self):
        assert _format_srt_time(0.001) == "00:00:00,001"

    def test_large_value(self):
        result = _format_srt_time(36000.999)
        assert result == "10:00:00,999"

    def test_uses_comma(self):
        assert "," in _format_srt_time(1.5)
        assert "." not in _format_srt_time(1.5)


class TestFormatVttTime:

    def test_zero(self):
        assert _format_vtt_time(0) == "00:00:00.000"

    def test_one_hour_plus(self):
        assert _format_vtt_time(3661.5) == "01:01:01.500"

    def test_uses_dot(self):
        assert "." in _format_vtt_time(1.5)
        assert "," not in _format_vtt_time(1.5)


# ============================================================
# _strip_subtitle_punct
# ============================================================

class TestStripSubtitlePunct:

    def test_strips_trailing_comma(self):
        assert _strip_subtitle_punct("你好，") == "你好"

    def test_strips_trailing_period(self):
        assert _strip_subtitle_punct("你好。") == "你好"

    def test_preserves_question_mark(self):
        assert _strip_subtitle_punct("你好？") == "你好？"

    def test_preserves_exclamation(self):
        assert _strip_subtitle_punct("你好！") == "你好！"

    def test_empty_string(self):
        assert _strip_subtitle_punct("") == ""

    def test_none(self):
        assert _strip_subtitle_punct(None) is None

    def test_no_trailing_punct(self):
        assert _strip_subtitle_punct("你好") == "你好"

    def test_multiple_trailing(self):
        assert _strip_subtitle_punct("你好。，；：") == "你好"


# ============================================================
# _format_txt
# ============================================================

class TestFormatTxt:

    def test_with_paragraphs(self):
        paragraphs = [
            Paragraph(index=1, text="第一段"),
            Paragraph(index=2, text="第二段"),
        ]
        result = _make_result("第一段第二段", paragraphs=paragraphs)
        assert _format_txt(result) == "第一段\n\n第二段"

    def test_without_paragraphs_fallback_to_text(self):
        result = _make_result("原始文本")
        assert _format_txt(result) == "原始文本"

    def test_empty_paragraphs_filtered(self):
        paragraphs = [
            Paragraph(index=1, text="有效段落"),
            Paragraph(index=2, text="   "),
        ]
        result = _make_result("有效段落", paragraphs=paragraphs)
        assert _format_txt(result) == "有效段落"


# ============================================================
# _format_srt
# ============================================================

class TestFormatSrt:

    def test_empty_segments_returns_text(self):
        result = _make_result("原始文本")
        assert _format_srt(result) == "原始文本"

    def test_single_segment(self):
        segs = [_make_segment(0.0, 5.0, "你好世界。")]
        result = _make_result("你好世界。", segments=segs)
        srt = _format_srt(result)

        assert "1\n" in srt
        assert "00:00:00,000 --> 00:00:05,000" in srt
        assert "你好世界" in srt

    def test_multiple_segments(self):
        segs = [
            _make_segment(0.0, 5.0, "第一句。"),
            _make_segment(5.5, 10.0, "第二句。"),
        ]
        result = _make_result("第一句。第二句。", segments=segs)
        srt = _format_srt(result)

        assert "1\n" in srt
        assert "2\n" in srt
        lines = srt.strip().split("\n")
        assert len(lines) >= 7

    def test_strips_trailing_punct(self):
        segs = [_make_segment(0.0, 5.0, "你好，")]
        result = _make_result("你好，", segments=segs)
        srt = _format_srt(result)
        assert srt.strip().split("\n")[-1] == "你好"


# ============================================================
# _format_vtt
# ============================================================

class TestFormatVtt:

    def test_empty_segments_returns_text(self):
        result = _make_result("原始文本")
        assert _format_vtt(result) == "原始文本"

    def test_header_present(self):
        segs = [_make_segment(0.0, 5.0, "测试")]
        result = _make_result("测试", segments=segs)
        vtt = _format_vtt(result)
        assert vtt.startswith("WEBVTT")

    def test_uses_dot_timestamp(self):
        segs = [_make_segment(0.0, 5.0, "测试")]
        result = _make_result("测试", segments=segs)
        vtt = _format_vtt(result)
        assert "00:00:00.000 --> 00:00:05.000" in vtt


# ============================================================
# _format_char_json
# ============================================================

class TestFormatCharJson:

    def test_top_level_char_timestamps(self):
        chars = [
            CharTimestamp(word="你", start=0.0, end=0.3),
            CharTimestamp(word="好", start=0.3, end=0.6),
        ]
        result = _make_result("你好", char_timestamps=chars)
        output = json.loads(_format_char_json(result))

        assert len(output) == 2
        assert output[0]["word"] == "你"
        assert output[0]["start"] == 0.0
        assert output[1]["word"] == "好"

    def test_segment_level_char_timestamps(self):
        chars = [CharTimestamp(word="测", start=0.0, end=0.5)]
        segs = [_make_segment(0.0, 0.5, "测", char_timestamps=chars)]
        result = _make_result("测", segments=segs)
        output = json.loads(_format_char_json(result))

        assert len(output) == 1
        assert output[0]["word"] == "测"

    def test_no_char_timestamps_returns_empty_array(self):
        result = _make_result("你好")
        assert _format_char_json(result) == "[]"

    def test_rounds_to_two_decimals(self):
        chars = [CharTimestamp(word="你", start=0.1234, end=0.5678)]
        result = _make_result("你", char_timestamps=chars)
        output = json.loads(_format_char_json(result))
        assert output[0]["start"] == 0.12
        assert output[0]["end"] == 0.57


# ============================================================
# _segment_by_punctuation
# ============================================================

class TestSegmentByPunctuation:

    def test_empty_char_timestamps(self):
        assert _segment_by_punctuation("文本", []) == []

    def test_sentence_end_breaks(self):
        chars = [
            CharTimestamp(word="你", start=0.0, end=0.3),
            CharTimestamp(word="好", start=0.3, end=0.6),
            CharTimestamp(word="世", start=0.6, end=0.9),
            CharTimestamp(word="界", start=0.9, end=1.2),
        ]
        result = _segment_by_punctuation("你好。世界", chars)
        assert len(result) >= 1
        assert result[0]["text"] == "你好"

    def test_no_punctuation_no_split(self):
        chars = [
            CharTimestamp(word="你", start=0.0, end=0.3),
            CharTimestamp(word="好", start=0.3, end=0.6),
        ]
        result = _segment_by_punctuation("你好", chars)
        assert len(result) == 1
        assert result[0]["text"] == "你好"


# ============================================================
# _format_volc_json
# ============================================================

class TestFormatVolcJson:

    def test_with_char_timestamps(self):
        chars = [
            CharTimestamp(word="你", start=0.0, end=0.3),
            CharTimestamp(word="好", start=0.3, end=0.6),
        ]
        result = _make_result("你好", char_timestamps=chars)
        output = json.loads(_format_volc_json(result))

        assert "segments" in output
        assert "words" in output
        assert len(output["words"]) == 2

    def test_empty_char_timestamps(self):
        result = _make_result("你好")
        output = json.loads(_format_volc_json(result))

        assert output["words"] == []

    def test_segment_fallback(self):
        chars = [CharTimestamp(word="测", start=0.0, end=0.5)]
        segs = [_make_segment(0.0, 0.5, "测", char_timestamps=chars)]
        result = _make_result("测", segments=segs)
        output = json.loads(_format_volc_json(result))

        assert len(output["words"]) == 1


# ============================================================
# format_output (main entry)
# ============================================================

class TestFormatOutput:

    def test_txt_format(self):
        result = _make_result("文本")
        assert format_output(result, OutputFormat.TXT) == "文本"

    def test_srt_format(self):
        segs = [_make_segment(0.0, 5.0, "测试")]
        result = _make_result("测试", segments=segs)
        output = format_output(result, OutputFormat.SRT)
        assert "-->" in output

    def test_vtt_format(self):
        segs = [_make_segment(0.0, 5.0, "测试")]
        result = _make_result("测试", segments=segs)
        output = format_output(result, OutputFormat.VTT)
        assert "WEBVTT" in output

    def test_char_json_format(self):
        chars = [CharTimestamp(word="你", start=0.0, end=0.3)]
        result = _make_result("你", char_timestamps=chars)
        output = format_output(result, OutputFormat.CHAR_JSON)
        parsed = json.loads(output)
        assert parsed[0]["word"] == "你"

    def test_volc_json_format(self):
        chars = [CharTimestamp(word="你", start=0.0, end=0.3)]
        result = _make_result("你", char_timestamps=chars)
        output = format_output(result, OutputFormat.VOLC_JSON)
        parsed = json.loads(output)
        assert "words" in parsed

    def test_json_default_format(self):
        result = _make_result("文本")
        output = format_output(result, OutputFormat.JSON)
        parsed = json.loads(output)
        assert parsed["text"] == "文本"

    def test_exception_fallback_to_text(self):
        result = _make_result("fallback text")
        with unittest.mock.patch("utils.output_formatter._format_txt", side_effect=RuntimeError("test")):
            output = format_output(result, OutputFormat.TXT)
            assert output == "fallback text"
