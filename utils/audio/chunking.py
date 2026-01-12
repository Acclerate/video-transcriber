"""
音频分块处理模块
将长音频分割成小块以提高语音识别的准确率和性能
使用 ffmpeg 进行快速分割
"""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List, Tuple, Optional

from loguru import logger


class AudioChunker:
    """音频分块处理器 - 使用 ffmpeg 快速分割"""

    def __init__(
        self,
        chunk_duration: int = 300,  # 5分钟
        overlap: int = 2,  # 2秒重叠
        min_duration_for_chunking: int = 600  # 10分钟以上才分块
    ):
        """
        初始化音频分块器

        Args:
            chunk_duration: 每块时长（秒）
            overlap: 块之间重叠时间（秒）
            min_duration_for_chunking: 最小分块时长（秒）
        """
        self.chunk_duration = chunk_duration
        self.overlap = overlap
        self.min_duration_for_chunking = min_duration_for_chunking

    def should_chunk(self, audio_path: str) -> bool:
        """
        判断是否需要对音频进行分块

        Args:
            audio_path: 音频文件路径

        Returns:
            bool: 是否需要分块
        """
        duration = self.get_audio_duration(audio_path)
        return duration > self.min_duration_for_chunking

    def get_audio_duration(self, audio_path: str) -> float:
        """
        获取音频时长（秒）- 使用 ffprobe

        Args:
            audio_path: 音频文件路径

        Returns:
            float: 时长（秒）
        """
        try:
            cmd = [
                'ffprobe', '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                return float(result.stdout.strip())
            else:
                logger.warning(f"ffprobe 获取音频时长失败: {result.stderr}")
                return 0.0
        except Exception as e:
            logger.error(f"获取音频时长失败: {e}")
            return 0.0

    async def split_audio(
        self,
        audio_path: str,
        temp_dir: str = None
    ) -> List[Tuple[str, float, float]]:
        """
        将音频分割成多个块 - 使用 ffmpeg 快速分割

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
            # 获取音频总时长
            total_duration = self.get_audio_duration(audio_path)
            logger.info(f"开始分割音频: 总时长 {total_duration:.1f} 秒")

            chunks = []
            start_time = 0.0
            chunk_index = 0

            while start_time < total_duration:
                # 计算块的结束时间
                end_time = min(start_time + self.chunk_duration, total_duration)

                # 跳过太小的块（小于300秒）
                if end_time - start_time < 300:
                    logger.debug(f"跳过太小的块: {start_time:.1f}s - {end_time:.1f}s")
                    break

                # 输出文件路径
                chunk_path = temp_path / f"chunk_{chunk_index}.wav"

                # 使用 ffmpeg 提取音频片段
                # 关键优化：-ss 作为输出选项，避免先跳转再解码
                duration = end_time - start_time
                cmd = [
                    'ffmpeg', '-y', '-v', 'error',
                    '-i', audio_path,
                    '-ss', str(start_time),  # 作为输出选项，更快
                    '-t', str(duration),
                    '-ar', '16000',  # 16kHz 采样率
                    '-ac', '1',       # 单声道
                    '-c:a', 'pcm_s16le',  # PCM 16-bit 编码
                    str(chunk_path)
                ]

                logger.info(f"创建块 {chunk_index}: {start_time:.1f}s - {end_time:.1f}s (时长 {duration:.1f}s)")

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
                if result.returncode != 0:
                    logger.error(f"ffmpeg 分割块 {chunk_index} 失败: {result.stderr}")
                    raise Exception(f"ffmpeg 分割失败: {result.stderr}")

                chunks.append((str(chunk_path), start_time, end_time))

                # 移动到下一块（减去重叠时间）
                # 如果到达末尾，退出循环
                if end_time >= total_duration - 1:
                    logger.debug(f"到达音频末尾，停止分割")
                    break

                start_time = end_time - self.overlap
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
    chunk_duration: int = 300,
    overlap: int = 2,
    min_duration: int = 600
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
