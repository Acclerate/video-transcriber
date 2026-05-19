"""
字幕时间修正测试
"""

from models.schemas import TranscriptionSegment
from utils.subtitle_timing import (
    fix_subtitle_segment_timing,
    anchor_segments_to_vad,
    enforce_silence_boundaries,
)


def _make_segment(start: float, end: float, text: str) -> TranscriptionSegment:
    return TranscriptionSegment.model_construct(
        start_time=start,
        end_time=end,
        text=text,
        confidence=0.95,
        char_timestamps=[],
    )


class TestSubtitleTiming:

    def test_merges_short_subtitle_into_previous_segment(self):
        segments = [
            _make_segment(0.0, 1.0, "第一句"),
            _make_segment(1.0, 1.3, "短"),
            _make_segment(1.3, 2.0, "第二句"),
        ]

        fixed, overlap_fixed = fix_subtitle_segment_timing(segments, subtitle_hold_seconds=0.35)

        assert overlap_fixed == 0
        assert len(fixed) == 2
        assert fixed[0].text == "第一句短"
        assert fixed[0].end_time == 1.3
        assert fixed[0].end_time <= fixed[1].start_time

    def test_merges_short_subtitle_into_next_when_previous_is_too_long(self):
        segments = [
            _make_segment(0.0, 4.0, "这是一段已经很长很长很长很长很长很长很长很长的字幕"),
            _make_segment(4.0, 4.3, "短"),
            _make_segment(4.3, 5.0, "第二句"),
        ]

        fixed, overlap_fixed = fix_subtitle_segment_timing(segments, subtitle_hold_seconds=0.35, max_chars=20)

        assert overlap_fixed == 0
        assert len(fixed) == 2
        assert fixed[1].text == "短第二句"
        assert fixed[0].end_time <= fixed[1].start_time

    def test_merges_short_subtitle_into_next_when_previous_would_be_too_long(self):
        segments = [
            _make_segment(0.0, 8.2, "第一句"),
            _make_segment(8.2, 8.5, "短"),
            _make_segment(8.5, 9.2, "第二句"),
        ]

        fixed, overlap_fixed = fix_subtitle_segment_timing(
            segments,
            subtitle_hold_seconds=0.35,
            max_duration_seconds=8.35,
        )

        assert overlap_fixed == 0
        assert len(fixed) == 2
        assert fixed[1].text == "短第二句"
        assert fixed[0].end_time <= fixed[1].start_time

    def test_extends_subtitle_end_without_overlap(self):
        segments = [
            _make_segment(0.0, 1.0, "第一句"),
            _make_segment(1.2, 2.0, "第二句"),
        ]

        fixed, overlap_fixed = fix_subtitle_segment_timing(segments, subtitle_hold_seconds=0.35)

        assert overlap_fixed == 0
        assert fixed[0].end_time == 1.2
        assert fixed[1].end_time == 2.35
        assert fixed[0].end_time <= fixed[1].start_time

    def test_keeps_existing_end_when_next_subtitle_starts_immediately(self):
        segments = [
            _make_segment(0.0, 1.0, "第一句"),
            _make_segment(1.0, 2.0, "第二句"),
        ]

        fixed, overlap_fixed = fix_subtitle_segment_timing(segments, subtitle_hold_seconds=0.35)

        assert overlap_fixed == 0
        assert fixed[0].end_time == 1.0
        assert fixed[1].end_time == 2.35
        assert fixed[0].end_time <= fixed[1].start_time


# ============================================================
# VAD 边界锚定
# ============================================================

class TestAnchorSegmentsToVad:

    def test_snap_start_forward(self):
        segs = [_make_segment(0.8, 3.0, "你好")]
        vads = [_make_segment(1.0, 3.0, "你好")]
        result = anchor_segments_to_vad(segs, vads, tolerance_seconds=0.3)
        assert result[0].start_time == 1.0

    def test_snap_end_backward(self):
        segs = [_make_segment(1.0, 3.5, "你好")]
        vads = [_make_segment(1.0, 3.0, "你好")]
        result = anchor_segments_to_vad(segs, vads, tolerance_seconds=0.6)
        assert result[0].end_time == 3.0

    def test_exceeds_tolerance_no_change(self):
        segs = [_make_segment(0.0, 3.0, "你好")]
        vads = [_make_segment(1.0, 3.0, "你好")]
        result = anchor_segments_to_vad(segs, vads, tolerance_seconds=0.2)
        assert result[0].start_time == 0.0

    def test_no_overlap_no_change(self):
        segs = [_make_segment(5.0, 8.0, "测试")]
        vads = [_make_segment(0.0, 3.0, "你好")]
        result = anchor_segments_to_vad(segs, vads)
        assert result[0].start_time == 5.0

    def test_empty_inputs(self):
        assert anchor_segments_to_vad([], []) == []
        assert anchor_segments_to_vad([_make_segment(0, 1, "a")], []) == [_make_segment(0, 1, "a")]

    def test_negative_duration_protection(self):
        segs = [_make_segment(1.0, 2.0, "测试")]
        vads = [_make_segment(1.5, 1.5, "测试")]
        result = anchor_segments_to_vad(segs, vads, tolerance_seconds=1.0)
        assert result[0].end_time > result[0].start_time


# ============================================================
# 静音区间约束
# ============================================================

class TestEnforceSilenceBoundaries:

    def test_start_in_silence_snap_forward(self):
        segs = [_make_segment(1.5, 4.0, "你好")]
        silences = [(1.0, 2.0)]
        result = enforce_silence_boundaries(segs, silences)
        assert result[0].start_time == 2.0

    def test_end_in_silence_snap_backward(self):
        segs = [_make_segment(0.0, 2.5, "你好")]
        silences = [(2.0, 3.0)]
        result = enforce_silence_boundaries(segs, silences)
        assert result[0].end_time == 2.0

    def test_valid_segment_unchanged(self):
        segs = [_make_segment(0.0, 2.0, "你好")]
        silences = [(3.0, 4.0)]
        result = enforce_silence_boundaries(segs, silences)
        assert result[0].start_time == 0.0
        assert result[0].end_time == 2.0

    def test_short_silence_skipped(self):
        segs = [_make_segment(1.0, 3.0, "你好")]
        silences = [(0.5, 0.54)]
        result = enforce_silence_boundaries(segs, silences, min_silence_margin=0.05)
        assert result[0].start_time == 1.0

    def test_empty_inputs(self):
        assert enforce_silence_boundaries([], []) == []
        assert enforce_silence_boundaries([_make_segment(0, 1, "a")], []) == [_make_segment(0, 1, "a")]
        assert enforce_silence_boundaries([], [(1, 2)]) == []

    def test_negative_duration_protection(self):
        segs = [_make_segment(1.5, 2.5, "你好")]
        silences = [(1.0, 2.0), (2.0, 3.0)]
        result = enforce_silence_boundaries(segs, silences)
        assert result[0].end_time > result[0].start_time
