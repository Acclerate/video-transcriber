"""
输出格式化工具
将转录结果格式化为不同格式 (TXT, SRT, VTT, JSON)
"""

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
            return result.text
        elif format_type == OutputFormat.SRT:
            return _format_srt(result)
        elif format_type == OutputFormat.VTT:
            return _format_vtt(result)
        else:  # JSON
            return result.model_dump_json(indent=2)

    except Exception as e:
        logger.error(f"输出格式化失败: {e}")
        return result.text  # 回退到纯文本


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
        srt_content.append(segment.text)
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
        vtt_content.append(segment.text)
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
