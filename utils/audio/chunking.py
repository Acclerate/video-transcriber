"""
音频分块处理模块
将长音频分割成小块以避免 Whisper 的重复/卡顿问题
"""

import os
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional
import asyncio

from loguru import logger

# 尝试导入 pydub，如果不可用则禁用分块功能
try:
    from pydub import AudioSegment
    PYDUB_AVAILABLE = True
except ImportError:
    PYDUB_AVAILABLE = False
    AudioSegment = None
    logger.warning(
        "pydub 未安装，音频分块功能将不可用。"
        "请运行: pip install pydub"
    )


class AudioChunker:
    """音频分块处理器"""

    def __init__(
        self,
        chunk_duration: int = 180,  # 3分钟
        overlap: int = 2,  # 2秒重叠
        min_duration_for_chunking: int = 300  # 5分钟以上才分块
    ):
        """
        初始化音频分块器

        Args:
            chunk_duration: 每块时长（秒）
            overlap: 块之间重叠时间（秒）
            min_duration_for_chunking: 最小分块时长（秒）
        """
        self.chunk_duration = chunk_duration * 1000  # 转换为毫秒
        self.overlap = overlap * 1000  # 转换为毫秒
        self.min_duration_for_chunking = min_duration_for_chunking * 1000

    def should_chunk(self, audio_path: str) -> bool:
        """
        判断是否需要对音频进行分块

        Args:
            audio_path: 音频文件路径

        Returns:
            bool: 是否需要分块
        """
        if not PYDUB_AVAILABLE:
            logger.warning("pydub 不可用，跳过分块处理")
            return False

        try:
            audio = AudioSegment.from_file(audio_path)
            duration_ms = len(audio)
            return duration_ms > self.min_duration_for_chunking
        except Exception as e:
            logger.warning(f"无法读取音频时长: {e}")
            return False

    def get_audio_duration(self, audio_path: str) -> float:
        """
        获取音频时长（秒）

        Args:
            audio_path: 音频文件路径

        Returns:
            float: 时长（秒）
        """
        if not PYDUB_AVAILABLE:
            logger.warning("pydub 不可用，无法获取音频时长")
            return 0.0

        try:
            audio = AudioSegment.from_file(audio_path)
            return len(audio) / 1000.0
        except Exception as e:
            logger.error(f"获取音频时长失败: {e}")
            return 0.0

    async def split_audio(
        self,
        audio_path: str,
        temp_dir: str = None
    ) -> List[Tuple[str, float, float]]:
        """
        将音频分割成多个块

        Args:
            audio_path: 音频文件路径
            temp_dir: 临时目录

        Returns:
            List[Tuple[str, float, float]]: (块文件路径, 开始时间, 结束时间) 列表
        """
        if not self.should_chunk(audio_path):
            # 不需要分块，返回原文件
            return [(audio_path, 0.0, self.get_audio_duration(audio_path))]

        temp_dir = temp_dir or tempfile.gettempdir()
        temp_path = Path(temp_dir)
        temp_path.mkdir(parents=True, exist_ok=True)

        try:
            # 加载音频
            audio = AudioSegment.from_file(audio_path)
            duration_ms = len(audio)

            logger.info(f"开始分割音频: 总时长 {duration_ms / 1000:.1f} 秒")

            chunks = []
            start_ms = 0
            chunk_index = 0

            while start_ms < duration_ms:
                # 计算块的结束时间
                end_ms = min(start_ms + self.chunk_duration, duration_ms)

                # 提取音频块
                chunk = audio[start_ms:end_ms]

                # 保存为临时文件
                chunk_path = temp_path / f"chunk_{chunk_index}.wav"
                chunk.export(chunk_path, format="wav")

                # 记录时间信息（秒）
                start_time = start_ms / 1000.0
                end_time = end_ms / 1000.0

                chunks.append((str(chunk_path), start_time, end_time))

                logger.debug(f"创建块 {chunk_index}: {start_time:.1f}s - {end_time:.1f}s")

                # 移动到下一块（减去重叠时间）
                start_ms = end_ms - self.overlap
                chunk_index += 1

            logger.info(f"音频分割完成: 共 {len(chunks)} 块")
            return chunks

        except Exception as e:
            logger.error(f"音频分割失败: {e}")
            # 失败时返回原文件
            return [(audio_path, 0.0, self.get_audio_duration(audio_path))]

    def merge_results(
        self,
        chunk_results: List[dict],
        overlap_seconds: float = 2.0
    ) -> dict:
        """
        合并多个块的转录结果

        Args:
            chunk_results: 块结果列表，每个包含 text, segments, start_time, end_time
            overlap_seconds: 重叠时间（秒），用于合并时去除重复

        Returns:
            dict: 合并后的结果
        """
        if not chunk_results:
            return {
                "text": "",
                "segments": [],
                "language": "unknown",
                "processing_time": 0.0
            }

        if len(chunk_results) == 1:
            return chunk_results[0]

        logger.info(f"合并 {len(chunk_results)} 个块的转录结果")

        merged_text = []
        merged_segments = []
        total_time = 0.0
        detected_language = "unknown"
        all_confidences = []

        # 用于跟踪时间偏移
        time_offset = 0.0

        for i, chunk_result in enumerate(chunk_results):
            chunk_text = chunk_result.get("text", "")
            chunk_segments = chunk_result.get("segments", [])
            chunk_language = chunk_result.get("language", "unknown")
            start_time = chunk_result.get("start_time", 0.0)
            end_time = chunk_result.get("end_time", 0.0)

            # 使用第一个块的语言作为总体语言
            if i == 0 and chunk_language != "unknown":
                detected_language = chunk_language

            # 累计处理时间
            total_time += chunk_result.get("processing_time", 0.0)

            # 对于第一个块，直接添加
            if i == 0:
                if chunk_text:
                    merged_text.append(chunk_text)
                for seg in chunk_segments:
                    merged_segments.append(seg)
            else:
                # 对于后续块，需要处理重叠
                # 调整时间戳
                for seg in chunk_segments:
                    seg["start"] = seg.get("start", 0) + time_offset
                    seg["end"] = seg.get("end", 0) + time_offset

                # 添加非重叠部分的文本
                # 简单处理：跳过第一段（通常是重叠部分）
                if len(chunk_segments) > 1:
                    # 跳过可能在重叠区域的第一段
                    segments_to_add = chunk_segments[1:]
                    for seg in segments_to_add:
                        merged_segments.append(seg)
                        if seg.get("text"):
                            merged_text.append(seg.get("text", ""))

            # 更新时间偏移（减去重叠时间）
            chunk_duration = end_time - start_time
            time_offset += chunk_duration - overlap_seconds

        # 合并文本
        final_text = " ".join(merged_text).strip()

        # 计算平均置信度
        for seg in merged_segments:
            conf = seg.get("confidence", 0)
            if conf:
                all_confidences.append(conf)

        avg_confidence = (
            sum(all_confidences) / len(all_confidences)
            if all_confidences else 0.5
        )

        result = {
            "text": final_text,
            "segments": merged_segments,
            "language": detected_language,
            "confidence": avg_confidence,
            "processing_time": total_time
        }

        logger.info(f"合并完成: 总文本长度 {len(final_text)} 字符")
        return result

    async def cleanup_chunks(self, chunk_paths: List[str]):
        """
        清理临时的音频块文件

        Args:
            chunk_paths: 块文件路径列表
        """
        for chunk_path in chunk_paths:
            try:
                # 只删除临时生成的块文件（不删除原始文件）
                if "chunk_" in os.path.basename(chunk_path):
                    Path(chunk_path).unlink(missing_ok=True)
                    logger.debug(f"已清理音频块: {chunk_path}")
            except Exception as e:
                logger.warning(f"清理音频块失败 {chunk_path}: {e}")


# 创建全局实例
audio_chunker = AudioChunker()


def get_audio_chunker(
    chunk_duration: int = 180,
    overlap: int = 2,
    min_duration: int = 300
) -> AudioChunker:
    """
    获取音频分块器实例

    Args:
        chunk_duration: 每块时长（秒）
        overlap: 重叠时间（秒）
        min_duration: 最小分块时长（秒）

    Returns:
        AudioChunker: 分块器实例
    """
    return AudioChunker(
        chunk_duration=chunk_duration,
        overlap=overlap,
        min_duration_for_chunking=min_duration
    )
