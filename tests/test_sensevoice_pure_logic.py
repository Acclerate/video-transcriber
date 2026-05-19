"""
SenseVoice 转录器纯逻辑测试
直接导入 core/sensevoice_transcriber.py 中的纯逻辑方法
不依赖 GPU/模型
"""

import pytest
from unittest.mock import patch

from models.schemas import Language, CharTimestamp


def _make_transcriber(**overrides):
    """构造一个跳过 __init__ 的 SenseVoiceTranscriber 实例"""
    from core.sensevoice_transcriber import SenseVoiceTranscriber
    t = SenseVoiceTranscriber.__new__(SenseVoiceTranscriber)
    defaults = {
        "clean_special_tokens": True,
        "device": "cpu",
        "silence_ranges": [],
    }
    defaults.update(overrides)
    for k, v in defaults.items():
        setattr(t, k, v)
    return t


# ============================================================
# _map_language
# ============================================================

class TestMapLanguage:

    def test_auto(self):
        t = _make_transcriber()
        assert t._map_language(Language.AUTO) == "auto"

    def test_chinese(self):
        t = _make_transcriber()
        assert t._map_language(Language.CHINESE) == "zh"

    def test_english(self):
        t = _make_transcriber()
        assert t._map_language(Language.ENGLISH) == "en"

    def test_japanese(self):
        t = _make_transcriber()
        assert t._map_language(Language.JAPANESE) == "ja"

    def test_korean(self):
        t = _make_transcriber()
        assert t._map_language(Language.KOREAN) == "ko"


# ============================================================
# _clean_special_tokens
# ============================================================

class TestCleanSpecialTokens:

    def test_language_tag(self):
        t = _make_transcriber()
        assert t._clean_special_tokens("<|zh|>你好世界") == "你好世界"

    def test_emotion_tag(self):
        t = _make_transcriber()
        assert t._clean_special_tokens("<|HAPPY|>太好了") == "太好了"

    def test_event_tag(self):
        t = _make_transcriber()
        assert t._clean_special_tokens("<|Speech|>说话内容") == "说话内容"

    def test_multiple_tags(self):
        t = _make_transcriber()
        result = t._clean_special_tokens("<|zh|><|NEUTRAL|>你好世界")
        assert result == "你好世界"

    def test_no_tags(self):
        t = _make_transcriber()
        assert t._clean_special_tokens("纯文本内容") == "纯文本内容"

    def test_empty_string(self):
        t = _make_transcriber()
        assert t._clean_special_tokens("") == ""

    def test_disabled(self):
        t = _make_transcriber(clean_special_tokens=False)
        text = "<|zh|>你好"
        assert t._clean_special_tokens(text) == text

    def test_cleans_extra_whitespace(self):
        t = _make_transcriber()
        assert t._clean_special_tokens("你好   世界") == "你好 世界"


# ============================================================
# _is_safe_subtitle_boundary
# ============================================================

class TestIsSafeSubtitleBoundary:

    def test_particle_next_char_unsafe(self):
        t = _make_transcriber()
        for ch in "的呢吧啊吗着过了":
            assert t._is_safe_subtitle_boundary("你好" + ch + "世界", 2) is False

    def test_preposition_prev_char_unsafe(self):
        t = _make_transcriber()
        for ch in "但和与及把被对在以从向给":
            text = "文本" + ch + "后面"
            assert t._is_safe_subtitle_boundary(text, 3) is False

    def test_normal_position_safe(self):
        t = _make_transcriber()
        assert t._is_safe_subtitle_boundary("你好世界", 2) is True

    def test_boundary_positions(self):
        t = _make_transcriber()
        assert t._is_safe_subtitle_boundary("你好", 0) is True
        assert t._is_safe_subtitle_boundary("你好", 2) is True


# ============================================================
# _subtitle_split_points_from_text
# ============================================================

class TestSubtitleSplitPointsFromText:

    def test_connector_word_detected(self):
        t = _make_transcriber()
        text = "前面有足够长的文字内容那么，接下来我们继续"
        points = t._subtitle_split_points_from_text(text)
        assert len(points) > 0

    def test_english_space_boundary(self):
        t = _make_transcriber()
        text = "这是一段足够长的中文文字 then we continue here"
        points = t._subtitle_split_points_from_text(text)
        # Should detect English space boundaries
        space_points = [p for p in points if text[p - 1:p + 1].strip() == "" or " " in text[max(0, p - 1):p + 1]]
        # At minimum we should have connector or space points
        assert len(points) > 0

    def test_short_text_no_points(self):
        t = _make_transcriber()
        text = "短文本"
        points = t._subtitle_split_points_from_text(text)
        assert len(points) == 0

    def test_plain_long_text(self):
        t = _make_transcriber()
        text = "这是一段没有任何连接词的纯中文长文本段落内容"
        points = t._subtitle_split_points_from_text(text)
        # No connector words, no spaces → no split points
        assert len(points) == 0


# ============================================================
# _find_natural_split
# ============================================================

class TestFindNaturalSplit:

    def test_finds_punctuation_forward(self):
        t = _make_transcriber()
        text = "你好世界，继续说"
        result = t._find_natural_split(text, 0, 2)
        assert result == 5  # position after comma

    def test_finds_punctuation_backward(self):
        t = _make_transcriber()
        text = "你，好世继续"
        result = t._find_natural_split(text, 0, 3)
        assert result == 2  # position after comma

    def test_english_space_boundary(self):
        t = _make_transcriber()
        text = "hello world test"
        result = t._find_natural_split(text, 0, 5)
        assert result == 6  # position after space

    def test_no_features_returns_target(self):
        t = _make_transcriber()
        text = "你好世界测试"
        result = t._find_natural_split(text, 0, 3)
        assert result == 3


# ============================================================
# _map_punctuation_positions
# ============================================================

class TestMapPunctuationPositions:

    def test_sentence_end(self):
        t = _make_transcriber()
        positions = t._map_punctuation_positions("你好世界", "你好世界。")
        assert 4 in positions
        assert positions[4] == "sentence_end"

    def test_clause_end(self):
        t = _make_transcriber()
        positions = t._map_punctuation_positions("你好世界", "你好，世界")
        assert 2 in positions
        assert positions[2] == "clause_end"

    def test_no_punctuation(self):
        t = _make_transcriber()
        positions = t._map_punctuation_positions("你好世界", "你好世界")
        assert len(positions) == 0

    def test_empty_strings(self):
        t = _make_transcriber()
        assert t._map_punctuation_positions("", "") == {}
        assert t._map_punctuation_positions("你好", "") == {}
        assert t._map_punctuation_positions("", "你好") == {}

    def test_mixed_punctuation(self):
        t = _make_transcriber()
        positions = t._map_punctuation_positions("你好世界测试", "你好，世界。测试！")
        assert positions.get(2) == "clause_end"
        assert positions.get(4) == "sentence_end"
        assert positions.get(6) == "sentence_end"


# ============================================================
# _build_rec_config
# ============================================================

class TestBuildRecConfig:

    def test_default_timestamp_mode(self):
        t = _make_transcriber()
        config = t._build_rec_config("zh")
        assert config["language"] == "zh"
        assert "output_timestamp" not in config

    def test_char_timestamp_mode(self):
        t = _make_transcriber()
        config = t._build_rec_config("zh", timestamp_mode="char")
        assert config["output_timestamp"] is True

    def test_sentence_timestamp_mode(self):
        t = _make_transcriber()
        config = t._build_rec_config("en", timestamp_mode="sentence")
        assert config["output_timestamp"] is True
        assert config["language"] == "en"

    def test_device_set(self):
        t = _make_transcriber(device="cuda")
        config = t._build_rec_config("auto")
        assert config["device"] == "cuda"
