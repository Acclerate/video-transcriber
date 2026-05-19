"""
强制对齐器纯逻辑测试
直接导入 utils/forced_aligner.py 中的实际函数（而非复制代码）
"""

import pytest

from models.schemas import CharTimestamp
from utils.forced_aligner import (
    _estimate_syllable_weight,
    _split_into_syllable_groups,
    distribute_timestamps_by_syllable,
    expand_char_timestamps_syllable_aware,
    ForcedAligner,
)


# ============================================================
# _estimate_syllable_weight
# ============================================================

class TestEstimateSyllableWeight:

    def test_chinese_full_weight(self):
        assert _estimate_syllable_weight("中") == 1.0
        assert _estimate_syllable_weight("文") == 1.0

    def test_digit(self):
        assert _estimate_syllable_weight("5") == 0.8

    def test_english_letter(self):
        assert _estimate_syllable_weight("a") == 0.85
        assert _estimate_syllable_weight("Z") == 0.85

    def test_hyphen_underscore(self):
        assert _estimate_syllable_weight("-") == 0.1
        assert _estimate_syllable_weight("_") == 0.1

    def test_punctuation(self):
        assert _estimate_syllable_weight(",") == 0.4
        assert _estimate_syllable_weight(".") == 0.4


# ============================================================
# _split_into_syllable_groups
# ============================================================

class TestSplitIntoSyllableGroups:

    def test_pure_chinese(self):
        groups = _split_into_syllable_groups("中文测试")
        assert len(groups) == 4
        assert all(w == 1.0 for _, w in groups)

    def test_pure_english_word(self):
        groups = _split_into_syllable_groups("hello")
        assert len(groups) == 1
        assert groups[0] == ("hello", 0.85 * 5)

    def test_mixed_chinese_english(self):
        groups = _split_into_syllable_groups("中hello文")
        assert len(groups) == 3
        assert groups[0] == ("中", 1.0)
        assert groups[1][0] == "hello"
        assert groups[2] == ("文", 1.0)

    def test_digits(self):
        groups = _split_into_syllable_groups("123")
        assert len(groups) == 1
        assert groups[0] == ("123", 0.8 * 3)

    def test_hyphen(self):
        groups = _split_into_syllable_groups("a-b")
        assert len(groups) == 3
        assert groups[1] == ("-", 0.1)


# ============================================================
# distribute_timestamps_by_syllable
# ============================================================

class TestDistributeTimestampsBySyllable:

    def test_single_char_returns_original(self):
        ts = CharTimestamp(word="中", start=0.0, end=1.0)
        result = distribute_timestamps_by_syllable(ts)
        assert len(result) == 1
        assert result[0].word == "中"

    def test_chinese_equal_distribution(self):
        ts = CharTimestamp(word="中文测试", start=0.0, end=4.0)
        result = distribute_timestamps_by_syllable(ts)
        assert len(result) == 4
        for i, char_ts in enumerate(result):
            assert char_ts.start == pytest.approx(i * 1.0)
            assert char_ts.end == pytest.approx((i + 1) * 1.0)

    def test_english_word_weighted(self):
        ts = CharTimestamp(word="hello", start=0.0, end=1.0)
        result = distribute_timestamps_by_syllable(ts)
        assert len(result) == 5
        for char_ts in result:
            assert pytest.approx(0.2) == char_ts.end - char_ts.start

    def test_invalid_timestamp_returns_original(self):
        ts = CharTimestamp(word="测试", start=5.0, end=3.0)
        result = distribute_timestamps_by_syllable(ts)
        assert len(result) == 1
        assert result[0].word == "测试"

    def test_empty_word_returns_empty(self):
        ts = CharTimestamp(word="", start=0.0, end=1.0)
        result = distribute_timestamps_by_syllable(ts)
        assert result == []


# ============================================================
# expand_char_timestamps_syllable_aware
# ============================================================

class TestExpandCharTimestampsSyllableAware:

    def test_empty_list(self):
        assert expand_char_timestamps_syllable_aware([]) == []

    def test_single_char_unchanged(self):
        ts = CharTimestamp(word="中", start=0.0, end=1.0)
        result = expand_char_timestamps_syllable_aware([ts])
        assert len(result) == 1
        assert result[0].word == "中"

    def test_multi_char_expanded(self):
        ts = CharTimestamp(word="中文", start=0.0, end=2.0)
        result = expand_char_timestamps_syllable_aware([ts])
        assert len(result) == 2
        assert result[0].word == "中"
        assert result[1].word == "文"

    def test_invalid_timestamp_kept(self):
        ts = CharTimestamp(word="test", start=5.0, end=3.0)
        result = expand_char_timestamps_syllable_aware([ts])
        assert len(result) == 1

    def test_mixed_valid_invalid(self):
        valid = CharTimestamp(word="好", start=0.0, end=1.0)
        invalid = CharTimestamp(word="test", start=5.0, end=3.0)
        result = expand_char_timestamps_syllable_aware([valid, invalid])
        assert result[0].word == "好"


# ============================================================
# ForcedAligner static methods
# ============================================================

class TestForcedAlignerStatic:

    def test_timestamp_to_seconds_normal(self):
        result = ForcedAligner._timestamp_to_seconds([1000, 2000], 0.0)
        assert result == (1.0, 2.0)

    def test_timestamp_to_seconds_with_offset(self):
        result = ForcedAligner._timestamp_to_seconds([1000, 2000], 5.0)
        assert result == (6.0, 7.0)

    def test_timestamp_to_seconds_with_force_shift(self):
        result = ForcedAligner._timestamp_to_seconds([1000, 2000], 0.0, force_time_shift=0.5)
        assert result == (1.5, 2.5)

    def test_timestamp_to_seconds_invalid_type(self):
        assert ForcedAligner._timestamp_to_seconds("invalid", 0.0) is None

    def test_timestamp_to_seconds_short_array(self):
        assert ForcedAligner._timestamp_to_seconds([100], 0.0) is None

    def test_timestamp_to_seconds_end_before_start(self):
        assert ForcedAligner._timestamp_to_seconds([2000, 1000], 0.0) is None

    def test_timestamp_to_seconds_non_numeric(self):
        assert ForcedAligner._timestamp_to_seconds(["a", "b"], 0.0) is None

    def test_timestamp_token(self):
        result = ForcedAligner._timestamp_token("中", 1.5, 2.5)
        assert result.word == "中"
        assert result.start == 1.5
        assert result.end == 2.5

    def test_timestamp_token_rounds(self):
        result = ForcedAligner._timestamp_token("中", 1.2345, 2.3456)
        assert result.start == 1.234
        assert result.end == 2.346

    def test_clean_alignment_text(self):
        text = "<|zh|>你好<|NEUTRAL|>世界"
        result = ForcedAligner._clean_alignment_text(text)
        assert "<|" not in result
        assert "你好" in result
        assert "世界" in result

    def test_clean_alignment_text_no_tokens(self):
        assert ForcedAligner._clean_alignment_text("纯文本") == "纯文本"
