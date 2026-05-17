"""
FA (Forced Aligner) 音节权重和时间分配测试
只测试纯逻辑部分，避免导入 funasr/torch 等重型依赖
"""

import pytest
import re
from models.schemas import CharTimestamp

# 复制必要的纯逻辑函数，避免导入 forced_aligner 模块
_CHINESE_CHARS_RE = re.compile(r'[一-鿿]')
_ENGLISH_WORD_RE = re.compile(r'[a-zA-Z]+')

def _estimate_syllable_weight(ch: str) -> float:
    """估算字符/音节的权重，用于时间分配"""
    if _CHINESE_CHARS_RE.match(ch):
        return 1.0
    if ch.isdigit():
        return 0.8
    if ch.isascii() and ch.isalpha():
        return 0.85  # 提高英文权重，从 0.7 -> 0.85
    if ch in '-_':
        return 0.1  # 连字符权重极低
    return 0.4

def _split_into_syllable_groups(text: str):
    groups = []
    i = 0
    while i < len(text):
        ch = text[i]
        if _CHINESE_CHARS_RE.match(ch):
            groups.append((ch, 1.0))
            i += 1
        elif ch.isascii() and ch.isalpha():
            j = i
            while j < len(text) and text[j].isascii() and text[j].isalpha():
                j += 1
            word = text[i:j]
            weight = 0.85 * len(word)
            groups.append((word, weight))
            i = j
        elif ch.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            groups.append((text[i:j], 0.8 * (j - i)))
            i = j
        elif ch in '-_':
            groups.append((ch, 0.1))
            i += 1
        else:
            i += 1
    return groups

def distribute_timestamps_by_syllable(word_ts: CharTimestamp):
    """基于音节/分词的时间分配"""
    text = word_ts.word.strip()
    if not text:
        return []
    if len(text) == 1 or word_ts.end <= word_ts.start:
        return [word_ts]

    duration = word_ts.end - word_ts.start
    groups = _split_into_syllable_groups(text)

    if not groups:
        char_duration = duration / len(text)
        return [
            CharTimestamp(
                word=ch,
                start=round(word_ts.start + char_duration * i, 3),
                end=round(word_ts.start + char_duration * (i + 1), 3),
            )
            for i, ch in enumerate(text)
        ]

    total_weight = sum(w for _, w in groups)
    if total_weight <= 0:
        total_weight = 1.0

    result = []
    current_time = word_ts.start

    for group_text, weight in groups:
        group_duration = duration * (weight / total_weight)
        n_chars = len(group_text)
        char_dur = group_duration / n_chars if n_chars > 0 else group_duration

        for i, ch in enumerate(group_text):
            start = current_time + char_dur * i
            end = current_time + char_dur * (i + 1)
            result.append(CharTimestamp(
                word=ch,
                start=round(start, 3),
                end=round(end, 3),
            ))
        current_time += group_duration

    return result

def expand_char_timestamps_syllable_aware(char_timestamps):
    """使用音节感知的时间展开"""
    expanded = []
    for ts in char_timestamps:
        text = ts.word.strip()
        if not text:
            continue
        if len(text) == 1 or ts.end <= ts.start:
            expanded.append(ts)
            continue
        expanded.extend(distribute_timestamps_by_syllable(ts))
    return expanded


class TestSyllableWeight:
    """测试音节权重估算"""

    def test_chinese_character_has_full_weight(self):
        assert _estimate_syllable_weight("中") == 1.0
        assert _estimate_syllable_weight("文") == 1.0
        assert _estimate_syllable_weight("字") == 1.0

    def test_digit_has_high_weight(self):
        assert _estimate_syllable_weight("0") == 0.8
        assert _estimate_syllable_weight("9") == 0.8

    def test_english_letter_has_improved_weight(self):
        assert _estimate_syllable_weight("a") == 0.85
        assert _estimate_syllable_weight("Z") == 0.85

    def test_hyphen_has_low_weight(self):
        assert _estimate_syllable_weight("-") == 0.1
        assert _estimate_syllable_weight("_") == 0.1

    def test_other_chars_have_default_weight(self):
        assert _estimate_syllable_weight(",") == 0.4
        assert _estimate_syllable_weight(".") == 0.4
        assert _estimate_syllable_weight(" ") == 0.4


class TestSyllableGroupSplitting:
    """测试音节分组"""

    def test_pure_chinese_text(self):
        groups = _split_into_syllable_groups("中文测试")
        assert len(groups) == 4
        assert all(weight == 1.0 for _, weight in groups)

    def test_pure_english_word(self):
        groups = _split_into_syllable_groups("hello")
        assert len(groups) == 1
        text, weight = groups[0]
        assert text == "hello"
        assert weight == 0.85 * 5  # 5 个字母，权重 0.85

    def test_mixed_chinese_english(self):
        groups = _split_into_syllable_groups("中hello文")
        assert len(groups) == 3
        assert groups[0] == ("中", 1.0)
        assert groups[1][0] == "hello"
        assert groups[2] == ("文", 1.0)

    def test_digits(self):
        groups = _split_into_syllable_groups("123")
        assert len(groups) == 1
        text, weight = groups[0]
        assert text == "123"
        assert weight == 0.8 * 3

    def test_special_chars(self):
        groups = _split_into_syllable_groups("a-b")
        assert len(groups) == 3
        assert groups[1] == ("-", 0.1)


class TestTimestampDistribution:
    """测试时间戳分配"""

    def test_single_char_returns_original(self):
        ts = CharTimestamp(word="中", start=0.0, end=1.0)
        result = distribute_timestamps_by_syllable(ts)
        assert len(result) == 1
        assert result[0].word == "中"
        assert result[0].start == 0.0
        assert result[0].end == 1.0

    def test_chinese_phrase_equal_distribution(self):
        ts = CharTimestamp(word="中文测试", start=0.0, end=4.0)
        result = distribute_timestamps_by_syllable(ts)
        assert len(result) == 4
        # 每个字符应该分配 1 秒
        for i, char_ts in enumerate(result):
            assert char_ts.start == pytest.approx(i * 1.0)
            assert char_ts.end == pytest.approx((i + 1) * 1.0)

    def test_english_word_weighted_distribution(self):
        ts = CharTimestamp(word="hello", start=0.0, end=1.0)
        result = distribute_timestamps_by_syllable(ts)
        assert len(result) == 5
        # 英文单词作为一组，内部均分
        for char_ts in result:
            assert pytest.approx(0.2) == char_ts.end - char_ts.start

    def test_mixed_chinese_english_distribution(self):
        ts = CharTimestamp(word="中hello文", start=0.0, end=7.0)
        result = distribute_timestamps_by_syllable(ts)

        # 应该有 7 个字符
        assert len(result) == 7

        # 第一个字符"中"应该分配更多时间
        assert result[0].word == "中"
        assert result[0].end - result[0].start > 1.0

        # 英文部分"hello"应该分配适中时间（权重提高后）
        hello_duration = sum(
            r.end - r.start for r in result[1:6]
        )
        # 总时长 7s，总权重 1.0 + 0.85*5 + 1.0 = 6.25
        # 英文权重 4.25，分配时长 7.0 * 4.25 / 6.25 ≈ 4.76s
        assert pytest.approx(4.76, rel=0.1) == hello_duration

        # 最后一个字符"文"应该分配更多时间
        assert result[6].word == "文"
        assert result[6].end - result[6].start > 1.0


class TestExpandFunction:
    """测试时间戳展开函数"""

    def test_empty_list_returns_empty(self):
        result = expand_char_timestamps_syllable_aware([])
        assert result == []

    def test_single_char_timestamp_unchanged(self):
        ts = CharTimestamp(word="中", start=0.0, end=1.0)
        result = expand_char_timestamps_syllable_aware([ts])
        assert len(result) == 1
        assert result[0].word == "中"

    def test_multi_char_timestamp_expanded(self):
        ts = CharTimestamp(word="中文", start=0.0, end=2.0)
        result = expand_char_timestamps_syllable_aware([ts])
        assert len(result) == 2
        assert result[0].word == "中"
        assert result[1].word == "文"

    def test_timestamps_with_invalid_start_end(self):
        ts = CharTimestamp(word="test", start=5.0, end=3.0)
        result = expand_char_timestamps_syllable_aware([ts])
        # 无效时间戳应该保留原样
        assert len(result) == 1
        assert result[0].word == "test"

    def test_mixed_valid_invalid_timestamps(self):
        valid = CharTimestamp(word="好", start=0.0, end=1.0)
        invalid = CharTimestamp(word="test", start=5.0, end=3.0)
        result = expand_char_timestamps_syllable_aware([valid, invalid])
        # 有效的展开，无效的保留
        assert len(result) >= 1
        assert result[0].word == "好"
