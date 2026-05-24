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
            new_end = max(round(cur.start_time, 3), prev.start_time + 0.001)
            cleaned[i - 1] = TranscriptionSegment(
                start_time=prev.start_time,
                end_time=new_end,
                text=prev.text,
                confidence=prev.confidence,
                char_timestamps=getattr(prev, "char_timestamps", []),
            )

    return cleaned, overlap_fixed


def anchor_segments_to_vad(
    segments: List[TranscriptionSegment],
    vad_segments: List[TranscriptionSegment],
    tolerance_seconds: float = 0.2,
) -> List[TranscriptionSegment]:
    """
    将字幕时间戳锚定到 VAD 语音段的边界。

    若字幕 start 在 VAD 段之前（落入静音），快进到 VAD start；
    若字幕 end 在 VAD 段之后，快退到 VAD end。
    仅在 tolerance 内才校正，避免误改。
    """
    if not segments or not vad_segments:
        return segments

    result = []
    for seg in segments:
        seg_start = seg.start_time
        seg_end = seg.end_time

        # 找到与该字幕重叠的 VAD 段
        for vad in vad_segments:
            # VAD 段必须与字幕有时间重叠
            if vad.end_time <= seg_start or vad.start_time >= seg_end:
                continue

            # 锚定 start：字幕在 VAD 之前开始，且差距在容差内
            if seg_start < vad.start_time and (vad.start_time - seg_start) <= tolerance_seconds:
                seg_start = vad.start_time

            # 锚定 end：字幕在 VAD 之后结束，且差距在容差内
            if seg_end > vad.end_time and (seg_end - vad.end_time) <= tolerance_seconds:
                seg_end = vad.end_time

            break

        # 确保正 duration
        if seg_end <= seg_start:
            seg_end = seg_start + 0.1

        result.append(TranscriptionSegment(
            start_time=round(seg_start, 3),
            end_time=round(seg_end, 3),
            text=seg.text,
            confidence=seg.confidence,
            char_timestamps=getattr(seg, "char_timestamps", []),
        ))

    return result


def enforce_silence_boundaries(
    segments: List[TranscriptionSegment],
    silence_ranges: List[Tuple[float, float]],
    min_silence_margin: float = 0.05,
) -> List[TranscriptionSegment]:
    """
    确保字幕时间戳不落入静音区间。

    若 start 在静音区间内，前移到静音结束点；
    若 end 在静音区间内，后移到静音起始点。
    """
    if not segments or not silence_ranges:
        return segments

    # 过滤过短的静音
    significant_silences = [
        (s, e) for s, e in silence_ranges if (e - s) >= min_silence_margin
    ]

    if not significant_silences:
        return segments

    result = []
    for seg in segments:
        seg_start = seg.start_time
        seg_end = seg.end_time

        for sil_start, sil_end in significant_silences:
            # start 落在静音区间内 → 前移到静音结束
            if sil_start <= seg_start < sil_end:
                seg_start = sil_end

            # end 落在静音区间内 → 后移到静音起始
            if sil_start < seg_end <= sil_end:
                seg_end = sil_start

        # 确保正 duration
        if seg_end <= seg_start:
            seg_end = seg_start + 0.1

        result.append(TranscriptionSegment(
            start_time=round(seg_start, 3),
            end_time=round(seg_end, 3),
            text=seg.text,
            confidence=seg.confidence,
            char_timestamps=getattr(seg, "char_timestamps", []),
        ))

    return result
