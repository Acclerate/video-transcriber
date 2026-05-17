"""
字幕时间修正工具
"""

from typing import List, Tuple, Optional

from models.schemas import TranscriptionSegment


def _calculate_segment_end(
    seg_start: float, seg_end: float, next_start: Optional[float], hold: float
) -> float:
    """计算片段结束时间，确保晚于开始时间"""
    end_time = min(seg_end + hold, next_start) if next_start is not None else seg_end + hold
    return max(end_time, seg_start + 0.1)


def fix_subtitle_segment_timing(
    segments: List[TranscriptionSegment],
    subtitle_hold_seconds: float = 0.2,
    min_duration_seconds: float = 0.5,
    max_chars: int = 25,
    max_duration_seconds: float = 5.0,
) -> Tuple[List[TranscriptionSegment], int]:
    cleaned = [seg for seg in segments if seg.text.strip()]
    overlap_fixed = 0

    i = 0
    while i < len(cleaned):
        seg = cleaned[i]
        if seg.end_time - seg.start_time >= min_duration_seconds or len(cleaned) == 1:
            i += 1
            continue

        merge_into_previous = i > 0
        if merge_into_previous and i + 1 < len(cleaned):
            prev = cleaned[i - 1]
            next_seg = cleaned[i + 1]
            prev_len = len(f"{prev.text}{seg.text}")
            next_len = len(f"{seg.text}{next_seg.text}")
            prev_duration = seg.end_time - prev.start_time
            next_duration = next_seg.end_time - seg.start_time
            if (
                prev_duration > max_duration_seconds
                or (prev_len > max_chars and next_len <= max_chars)
            ) and next_duration <= max_duration_seconds:
                merge_into_previous = False

        if merge_into_previous:
            prev = cleaned[i - 1]
            new_end = max(seg.end_time, prev.end_time) or prev.start_time + 0.1
            cleaned[i - 1] = TranscriptionSegment(
                start_time=prev.start_time,
                end_time=new_end,
                text=f"{prev.text}{seg.text}",
                confidence=prev.confidence,
                char_timestamps=getattr(prev, "char_timestamps", []) + getattr(seg, "char_timestamps", []),
            )
            cleaned.pop(i)
            continue

        next_seg = cleaned[i + 1]
        new_end = max(next_seg.end_time, seg.end_time) or seg.start_time + 0.1
        cleaned[i + 1] = TranscriptionSegment(
            start_time=seg.start_time,
            end_time=new_end,
            text=f"{seg.text}{next_seg.text}",
            confidence=next_seg.confidence,
            char_timestamps=getattr(seg, "char_timestamps", []) + getattr(next_seg, "char_timestamps", []),
        )
        cleaned.pop(i)

    for i, seg in enumerate(cleaned):
        next_start = cleaned[i + 1].start_time if i + 1 < len(cleaned) else None
        end_time = _calculate_segment_end(seg.start_time, seg.end_time, next_start, subtitle_hold_seconds)
        cleaned[i] = TranscriptionSegment(
            start_time=seg.start_time,
            end_time=round(end_time, 3),
            text=seg.text,
            confidence=seg.confidence,
            char_timestamps=getattr(seg, "char_timestamps", []),
        )

    for i in range(1, len(cleaned)):
        prev = cleaned[i - 1]
        cur = cleaned[i]
        if cur.start_time < prev.end_time:
            overlap_fixed += 1
            cleaned[i - 1] = TranscriptionSegment(
                start_time=prev.start_time,
                end_time=round(cur.start_time, 3),
                text=prev.text,
                confidence=prev.confidence,
                char_timestamps=getattr(prev, "char_timestamps", []),
            )

    return cleaned, overlap_fixed
