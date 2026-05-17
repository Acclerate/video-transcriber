"""
字幕时间修正测试
"""

from models.schemas import TranscriptionSegment
from utils.subtitle_timing import fix_subtitle_segment_timing


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
