"""
输出格式化工具
将转录结果格式化为不同格式 (TXT, SRT, VTT, JSON, CHAR_JSON, VOLC_JSON)
"""

import json
from loguru import logger
from models.schemas import TranscriptionResult, OutputFormat


def format_output(result: TranscriptionResult, format_type: OutputFormat = OutputFormat.JSON) -> str:
    """
    格式化输出结果

    Args:
        result: 转录结果
        format_type: 输出格式

    Returns:
        str: 格式化后的字符串
    """
    try:
        if format_type == OutputFormat.TXT:
            return _format_txt(result)
        elif format_type == OutputFormat.SRT:
            return _format_srt(result)
        elif format_type == OutputFormat.VTT:
            return _format_vtt(result)
        elif format_type == OutputFormat.CHAR_JSON:
            return _format_char_json(result)
        elif format_type == OutputFormat.VOLC_JSON:
            return _format_volc_json(result)
        else:  # JSON
            return result.model_dump_json(indent=2)

    except Exception as e:
        logger.error(f"输出格式化失败: {e}")
        return result.text  # 回退到纯文本


def _format_char_json(result: TranscriptionResult) -> str:
    """格式化为逐字时间戳 JSON: [{"word": "中", "start": 1.28, "end": 1.48}, ...]"""
    if result.char_timestamps:
        char_data = [
            {"word": ts.word, "start": round(ts.start, 2), "end": round(ts.end, 2)}
            for ts in result.char_timestamps
        ]
        return json.dumps(char_data, ensure_ascii=False, indent=2)

    # 回退：从 segments 的 char_timestamps 中收集
    all_chars = []
    for seg in result.segments:
        if seg.char_timestamps:
            all_chars.extend([
                {"word": ts.word, "start": round(ts.start, 2), "end": round(ts.end, 2)}
                for ts in seg.char_timestamps
            ])

    if all_chars:
        return json.dumps(all_chars, ensure_ascii=False, indent=2)

    return "[]"


# 句子分隔标点
_SENTENCE_END = set('。！？!?')
_CLAUSE_END = set('，,；;：:、')


def _segment_by_punctuation(
    text: str,
    char_timestamps: list,
    max_segment_chars: int = 40,
) -> list:
    """
    根据标点符号将文本和逐字时间戳分割为句子级片段。

    优先在句号/感叹号/问号处断句，其次在逗号处断句。
    当当前片段超过 max_segment_chars 且遇到逗号时也会断句。
    """
    if not char_timestamps:
        return []

    segments = []
    seg_chars = []
    seg_start = char_timestamps[0].start if hasattr(char_timestamps[0], 'start') else char_timestamps[0]["start"]
    ts_idx = 0

    def flush(end_ts):
        if not seg_chars:
            return
        start_val = seg_start if isinstance(seg_start, (int, float)) else seg_start
        end_val = end_ts.end if hasattr(end_ts, 'end') else end_ts["end"]
        segments.append({
            "start": round(start_val, 2),
            "end": round(end_val, 2),
            "text": "".join(seg_chars),
        })

    for ch in text:
        if ch in _SENTENCE_END | _CLAUSE_END:
            # 标点处断句：句末标点必断；逗号在片段较长时也断
            if ch in _SENTENCE_END or len(seg_chars) >= max_segment_chars:
                if seg_chars and ts_idx > 0:
                    last_ts = char_timestamps[ts_idx - 1]
                    flush(last_ts)
                seg_chars = []
                if ts_idx < len(char_timestamps):
                    seg_start = char_timestamps[ts_idx].start if hasattr(char_timestamps[ts_idx], 'start') else char_timestamps[ts_idx]["start"]
            continue

        # 非标点字符，对应一个 char_timestamp
        if ts_idx < len(char_timestamps):
            ts = char_timestamps[ts_idx]
            word = ts.word if hasattr(ts, 'word') else ts["word"]
            if ch == word:
                if not seg_chars:
                    seg_start = ts.start if hasattr(ts, 'start') else ts["start"]
                seg_chars.append(ch)
                ts_idx += 1

    # 处理剩余文本
    if seg_chars and ts_idx > 0:
        flush(char_timestamps[ts_idx - 1])

    return segments


def _format_volc_json(result: TranscriptionResult) -> str:
    """
    格式化为 volc.json 格式：
    {
      "segments": [{"start": 1.28, "end": 3.28, "text": "..."}],
      "words": [{"word": "中", "start": 1.28, "end": 1.48}, ...]
    }
    """
    # 收集 words
    words = []
    char_ts = result.char_timestamps
    if not char_ts:
        for seg in result.segments:
            if seg.char_timestamps:
                char_ts.extend(seg.char_timestamps)

    for ts in char_ts:
        words.append({
            "word": ts.word,
            "start": round(ts.start, 2),
            "end": round(ts.end, 2),
        })

    # 生成句子级片段
    segments = _segment_by_punctuation(result.text, char_ts)

    output = {
        "segments": segments,
        "words": words,
    }
    return json.dumps(output, ensure_ascii=False, indent=2)


def _format_txt(result: TranscriptionResult) -> str:
    """格式化为纯文本，段落间双换行"""
    if result.paragraphs:
        return "\n\n".join(p.text for p in result.paragraphs if p.text.strip())
    return result.text


def _strip_subtitle_punct(text: str) -> str:
    """去掉字幕末尾的标点（问号和感叹号保留）

    Netflix/BBC/中文字幕组规范：句尾不加句号/逗号
    """
    return text.rstrip("。，、；：,.;:") if text else text


def _format_srt(result: TranscriptionResult) -> str:
    """格式化为SRT字幕格式"""
    if not result.segments:
        return result.text

    srt_content = []
    for i, segment in enumerate(result.segments, 1):
        start_time = _format_srt_time(segment.start_time)
        end_time = _format_srt_time(segment.end_time)
        srt_content.append(f"{i}")
        srt_content.append(f"{start_time} --> {end_time}")
        srt_content.append(_strip_subtitle_punct(segment.text))
        srt_content.append("")  # 空行

    return "\n".join(srt_content)


def _format_vtt(result: TranscriptionResult) -> str:
    """格式化为VTT字幕格式"""
    if not result.segments:
        return result.text

    vtt_content = ["WEBVTT", ""]
    for segment in result.segments:
        start_time = _format_vtt_time(segment.start_time)
        end_time = _format_vtt_time(segment.end_time)
        vtt_content.append(f"{start_time} --> {end_time}")
        vtt_content.append(_strip_subtitle_punct(segment.text))
        vtt_content.append("")  # 空行

    return "\n".join(vtt_content)


def _format_srt_time(seconds: float) -> str:
    """格式化SRT时间戳 (HH:MM:SS,mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _format_vtt_time(seconds: float) -> str:
    """格式化VTT时间戳 (HH:MM:SS.mmm)"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"
