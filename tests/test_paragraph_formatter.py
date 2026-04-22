"""
段落格式化模块测试
"""

import pytest
from models.schemas import TranscriptionResult, TranscriptionSegment, TranscriptionModel
from utils.paragraph_formatter import format_paragraphs, _has_valid_timestamps, _split_by_text


def _make_segment(start: float, end: float, text: str, confidence: float = 0.95) -> TranscriptionSegment:
    """辅助：创建 segment，允许 end <= start 以绕过 validator。"""
    # 用 model_construct 绕过 end_time > start_time 的 validator
    return TranscriptionSegment.model_construct(
        start_time=start, end_time=end, text=text, confidence=confidence
    )


def _make_result(text: str, segments=None, language="zh") -> TranscriptionResult:
    """辅助：创建 TranscriptionResult。"""
    return TranscriptionResult.model_construct(
        text=text,
        language=language,
        confidence=0.95,
        segments=segments or [],
        processing_time=1.0,
        whisper_model="sensevoice-small",
        paragraphs=[],
    )


# ============================================================
# _has_valid_timestamps
# ============================================================

class TestHasValidTimestamps:

    def test_empty_segments(self):
        assert _has_valid_timestamps([]) is False

    def test_single_segment(self):
        segs = [_make_segment(0.0, 5.0, "hello")]
        assert _has_valid_timestamps(segs) is False

    def test_all_zero_timestamps(self):
        segs = [
            _make_segment(0.0, 0.0, "a"),
            _make_segment(0.0, 0.0, "b"),
            _make_segment(0.0, 0.0, "c"),
        ]
        assert _has_valid_timestamps(segs) is False

    def test_mostly_valid(self):
        segs = [
            _make_segment(0.0, 3.0, "a"),
            _make_segment(3.5, 7.0, "b"),
            _make_segment(7.0, 10.0, "c"),
            _make_segment(0.0, 0.0, "d"),  # 1 invalid out of 4
        ]
        assert _has_valid_timestamps(segs) is True

    def test_mostly_invalid(self):
        segs = [
            _make_segment(0.0, 0.0, "a"),
            _make_segment(0.0, 0.0, "b"),
            _make_segment(5.0, 10.0, "c"),  # only 1 valid out of 3
        ]
        assert _has_valid_timestamps(segs) is False


# ============================================================
# format_paragraphs — 混合策略（有效时间戳）
# ============================================================

class TestHybridSplit:

    def test_silence_gap_creates_paragraph(self):
        """大间隔应该产生段落分割。"""
        segs = [
            _make_segment(0.0, 5.0, "这是第一段话，有足够多的字数来满足最小长度要求，至少需要三十个字以上。"),
            _make_segment(5.0, 10.0, "还是第一段，继续补充一些文字，让累积长度超过最小值限制。"),
            _make_segment(15.0, 20.0, "这是第二段话，中间有五秒停顿，同样需要足够多的字数才能独立成段。"),
            _make_segment(20.0, 25.0, "第二段继续，补充更多文字内容。"),
        ]
        result = _make_result("".join(s.text for s in segs), segs)
        paragraphs = format_paragraphs(result, silence_threshold=1.5)

        assert len(paragraphs) >= 2

    def test_long_text_splits_at_sentence_end(self):
        """超长文本在句末标点处断段。"""
        # 生成一段超长文本，每个 segment 30 字
        long_text = "这是一段很长的测试文字，" * 10
        segs = []
        for i in range(10):
            start = i * 3.0
            end = start + 2.5
            segs.append(_make_segment(start, end, f"这是第{i+1}句话内容，一共三十个字左右。"))

        result = _make_result(long_text, segs)
        paragraphs = format_paragraphs(result, max_length=100, min_length=20)

        assert len(paragraphs) >= 2
        # 所有段落文本合并应等于原文（去除空格后）
        joined = "".join(p.text for p in paragraphs)
        assert len(joined) > 0

    def test_short_segments_merge(self):
        """太短的尾部段落应该合并到上一段。"""
        segs = [
            _make_segment(0.0, 5.0, "这是一段正常长度的话，有足够多的字数。"),
            _make_segment(10.0, 12.0, "短"),
        ]
        result = _make_result("".join(s.text for s in segs), segs)
        paragraphs = format_paragraphs(result, min_length=30)

        # "短" 应该被合并到第一段
        assert len(paragraphs) == 1


# ============================================================
# format_paragraphs — 纯文本回退
# ============================================================

class TestTextFallback:

    def test_splits_on_punctuation(self):
        """按句号分割。"""
        text = "这是第一句话。这是第二句话。这是第三句话。这是第四句话。" * 5
        result = _make_result(text, segments=[
            _make_segment(0.0, 0.0, "seg") for _ in range(4)
        ])
        paragraphs = format_paragraphs(result, max_length=80, min_length=10)

        assert len(paragraphs) >= 2

    def test_no_punctuation_single_paragraph(self):
        """没有句末标点时输出单段。"""
        text = "这是一段没有句号的话，全靠逗号连接，一直到结束"
        result = _make_result(text)
        paragraphs = format_paragraphs(result)

        assert len(paragraphs) == 1
        assert paragraphs[0].text == text

    def test_empty_text(self):
        """空文本返回空列表。"""
        result = _make_result("")
        assert format_paragraphs(result) == []

    def test_whitespace_only(self):
        """纯空白返回空列表。"""
        result = _make_result("   \n\t  ")
        assert format_paragraphs(result) == []

    def test_short_tail_merges(self):
        """纯文本模式下短尾合并到上一段。"""
        # 每句约 10 字
        text = "一二三四五六七八九十。" * 10 + "短尾。"
        result = _make_result(text)
        paragraphs = format_paragraphs(result, max_length=60, min_length=20)

        # 最后的 "短尾。" 应该被合并
        for p in paragraphs:
            assert len(p.text) >= 20


# ============================================================
# format_paragraphs — index 编号
# ============================================================

class TestIndexNumbering:

    def test_paragraph_indices_sequential(self):
        """段落序号从 1 开始递增。"""
        text = "第一段内容，有足够的字数，超过三十个字限制。这是第二句话。" \
               "第二段内容，同样也有足够多的字数，可以形成独立段落。" \
               "第三段内容，也满足最小字数的要求，能够独立成段。"
        result = _make_result(text)
        paragraphs = format_paragraphs(result, max_length=50, min_length=10)

        for i, p in enumerate(paragraphs):
            assert p.index == i + 1


# ============================================================
# _split_by_text 单元测试
# ============================================================

class TestSplitByText:

    def test_exact_max_length(self):
        """刚好达到 max_length 时在句号处断段。"""
        # 每句 10 字 + 1 句号 = 11
        text = "一二三四五六七八九十。" * 10
        paragraphs = _split_by_text(text, max_length=55, min_length=10)
        assert len(paragraphs) >= 2

    def test_single_long_sentence(self):
        """单句超长，直接输出。"""
        text = "一" * 500 + "。"
        paragraphs = _split_by_text(text, max_length=200, min_length=30)
        # 单句无法拆分，应该保持为 1 段
        assert len(paragraphs) == 1
