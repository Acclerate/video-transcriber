"""
段落格式化模块
将转录结果按语义和时间间隔分割为可读段落
混合策略：时间间隔 + 标点/字数，时间戳不可用时回退纯文本规则
"""

import re
from typing import List, Optional

from loguru import logger

from models.schemas import TranscriptionResult, TranscriptionSegment, Paragraph


# 中文句末标点
_SENTENCE_END_RE = re.compile(r'[。！？；…]+$')


def format_paragraphs(
    result: TranscriptionResult,
    silence_threshold: float = 1.5,
    max_length: int = 250,
    min_length: int = 30,
) -> List[Paragraph]:
    """
    将转录结果分割为段落列表。

    优先使用 segment 时间间隔 + 文本长度混合策略；
    当时间戳不可用时回退到纯文本规则（标点 + 字数）。

    Args:
        result: 转录结果
        silence_threshold: 相邻 segment 静音间隔阈值（秒）
        max_length: 段落最大字数
        min_length: 段落最小字数

    Returns:
        List[Paragraph]: 段落列表
    """
    if not result.text or not result.text.strip():
        return []

    if _has_valid_timestamps(result.segments):
        paragraphs = _split_by_hybrid(
            result.segments, result.text,
            silence_threshold=silence_threshold,
            max_length=max_length,
            min_length=min_length,
        )
    else:
        paragraphs = _split_by_text(
            result.text,
            max_length=max_length,
            min_length=min_length,
        )

    # 编号与日志
    for i, p in enumerate(paragraphs):
        p.index = i + 1

    logger.info(
        f"段落格式化完成: {len(paragraphs)} 段, "
        f"原文 {len(result.text)} 字"
    )
    return paragraphs


# ------------------------------------------------------------------
# 内部辅助
# ------------------------------------------------------------------

def _has_valid_timestamps(segments: List[TranscriptionSegment]) -> bool:
    """检查 segments 是否包含可用的时间间隔数据。

    至少 50% 的 segment 拥有非零且递增的时间戳才视为有效。
    """
    if not segments or len(segments) < 2:
        return False

    valid = 0
    for seg in segments:
        if seg.start_time > 0 and seg.end_time > seg.start_time:
            valid += 1

    return valid / len(segments) >= 0.5


def _split_by_hybrid(
    segments: List[TranscriptionSegment],
    full_text: str,
    silence_threshold: float,
    max_length: int,
    min_length: int,
) -> List[Paragraph]:
    """
    混合策略段落分割。

    断段条件：
    1. 相邻 segment 间隔 > silence_threshold（自然停顿）
    2. 累积文本长度 > max_length 且当前位置是句末标点

    同时满足 min_length 约束，避免产生过短段落。
    """
    paragraphs: List[Paragraph] = []
    current_texts: List[str] = []
    current_segs: List[TranscriptionSegment] = []
    current_length = 0

    for i, seg in enumerate(segments):
        gap = 0.0
        if i > 0:
            gap = seg.start_time - segments[i - 1].end_time

        should_break = False

        # 条件 1：自然停顿
        if gap > silence_threshold:
            should_break = True
        # 条件 2：超长段落 + 句末标点
        elif current_length >= max_length and _SENTENCE_END_RE.search(seg.text):
            should_break = True

        # 执行断段（前提：累积长度达到最小值）
        if should_break and current_length >= min_length and current_texts:
            paragraphs.append(_build_paragraph(
                current_texts, current_segs, len(paragraphs) + 1
            ))
            current_texts = []
            current_segs = []
            current_length = 0

        # 追加当前 segment
        seg_text = seg.text.strip()
        if seg_text:
            current_texts.append(seg_text)
            current_segs.append(seg)
            current_length += len(seg_text)

    # 处理剩余内容：如果太短则合并到上一段
    if current_texts:
        remaining_text = "".join(current_texts)
        if len(remaining_text) < min_length and paragraphs:
            # 合并到上一段落
            last = paragraphs[-1]
            last.text += remaining_text
            last.segments.extend(current_segs)
            if current_segs:
                last_seg = current_segs[-1]
                if last_seg.end_time > 0:
                    last.end_time = last_seg.end_time
        else:
            paragraphs.append(_build_paragraph(
                current_texts, current_segs, len(paragraphs) + 1
            ))

    # 后处理：如果最终段落为空则移除
    paragraphs = [p for p in paragraphs if p.text.strip()]

    return paragraphs


def _split_by_text(
    text: str,
    max_length: int,
    min_length: int,
) -> List[Paragraph]:
    """
    纯文本段落分割（回退策略）。

    按句末标点拆句，再按字数上限组段。
    """
    # 按句末标点拆分句子
    parts = re.split(r'([。！？；]+)', text)

    sentence_list: List[str] = []
    i = 0
    while i < len(parts):
        s = parts[i]
        # 如果下一个部分是句末标点，合并
        if i + 1 < len(parts) and re.match(r'[。！？；]+', parts[i + 1]):
            s += parts[i + 1]
            i += 2
        else:
            i += 1
        s = s.strip()
        if s:
            sentence_list.append(s)

    if not sentence_list:
        # 没有句末标点，整段输出
        return [Paragraph(index=1, text=text.strip())]

    paragraphs: List[Paragraph] = []
    current = ""

    for sentence in sentence_list:
        candidate = current + sentence

        if len(candidate) >= max_length and len(current) >= min_length:
            paragraphs.append(Paragraph(
                index=0,
                text=current.strip(),
            ))
            current = sentence
        else:
            current = candidate

    # 处理剩余
    if current.strip():
        remaining = current.strip()
        if len(remaining) < min_length and paragraphs:
            paragraphs[-1].text += remaining
        else:
            paragraphs.append(Paragraph(index=0, text=remaining))

    return paragraphs


def _build_paragraph(
    texts: List[str],
    segments: List[TranscriptionSegment],
    index: int,
) -> Paragraph:
    """根据累积的文本和 segments 构建一个 Paragraph 对象。"""
    para_text = "".join(texts)

    start_time = None
    end_time = None
    valid_segs = [s for s in segments if s.start_time > 0 or s.end_time > 0]
    if valid_segs:
        start_time = valid_segs[0].start_time if valid_segs[0].start_time > 0 else None
        end_time = valid_segs[-1].end_time if valid_segs[-1].end_time > 0 else None

    return Paragraph(
        index=index,
        text=para_text,
        start_time=start_time,
        end_time=end_time,
        segments=list(segments),
    )
