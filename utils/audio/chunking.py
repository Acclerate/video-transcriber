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
from utils.ffmpeg import get_ffmpeg_path, get_ffprobe_path


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
            ffprobe = get_ffprobe_path() or "ffprobe"
            cmd = [
                ffprobe, '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                audio_path
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            if result.returncode == 0:
                return float(result.stdout.decode("utf-8", errors="replace").strip())
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

                # 跳过太小的块（小于10秒）
                if end_time - start_time < 10:
                    logger.debug(f"跳过太小的块: {start_time:.1f}s - {end_time:.1f}s")
                    break

                # 输出文件路径
                chunk_path = temp_path / f"chunk_{chunk_index}.wav"

                # 使用 ffmpeg 提取音频片段
                ffmpeg = get_ffmpeg_path() or "ffmpeg"
                duration = end_time - start_time
                cmd = [
                    ffmpeg, '-y', '-v', 'error',
                    '-i', audio_path,
                    '-ss', str(start_time),
                    '-t', str(duration),
                    '-ar', '16000',
                    '-ac', '1',
                    '-c:a', 'pcm_s16le',
                    str(chunk_path)
                ]

                logger.info(f"创建块 {chunk_index}: {start_time:.1f}s - {end_time:.1f}s (时长 {duration:.1f}s)")

                result = subprocess.run(cmd, capture_output=True, timeout=120)
                if result.returncode != 0:
                    stderr_text = result.stderr.decode("utf-8", errors="replace")
                    logger.error(f"ffmpeg 分割块 {chunk_index} 失败: {stderr_text}")
                    raise Exception(f"ffmpeg 分割失败: {stderr_text}")

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
        merged_char_timestamps = []
        merged_vad_segments = []
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
            chunk_char_ts = chunk_result.get("char_timestamps", [])
            chunk_vad_segs = chunk_result.get("vad_segments", [])

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
                # 逐字时间戳：直接添加
                merged_char_timestamps.extend(chunk_char_ts)
                # VAD 分段：直接添加
                merged_vad_segments.extend(chunk_vad_segs)
            else:
                # 对于后续块，需要处理重叠
                # 调整时间戳
                for seg in chunk_segments:
                    seg["start"] = seg.get("start", 0) + time_offset
                    seg["end"] = seg.get("end", 0) + time_offset

                # 逐字时间戳：已由转录阶段转换为全局时间，这里只去除重叠
                if chunk_char_ts:
                    for ts in chunk_char_ts:
                        if merged_char_timestamps and ts["start"] <= merged_char_timestamps[-1]["end"]:
                            continue
                        merged_char_timestamps.append({
                            "word": ts["word"],
                            "start": round(ts["start"], 3),
                            "end": round(ts["end"], 3)
                        })

                # VAD 分段：合并重叠区段，只扩展时间范围不替换文本
                # 保持原始文本不变，确保 VAD 文本与 raw_text 开头对齐
                if chunk_vad_segs:
                    for vad_seg in chunk_vad_segs:
                        if merged_vad_segments and vad_seg["start_time"] < merged_vad_segments[-1]["end_time"]:
                            last = merged_vad_segments[-1]
                            last["end_time"] = max(last["end_time"], vad_seg["end_time"])
                            continue
                        merged_vad_segments.append(vad_seg)

                # 添加非重叠部分的文本
                # 如果有 segments，从 segments 中提取
                if len(chunk_segments) > 1:
                    # 跳过可能在重叠区域的第一段
                    segments_to_add = chunk_segments[1:]
                    for seg in segments_to_add:
                        merged_segments.append(seg)
                        if seg.get("text"):
                            merged_text.append(seg.get("text", ""))
                # 如果没有 segments 但有 text，直接添加 text
                elif chunk_text:
                    # 有文本但没有 segments 时，直接添加文本
                    # 注意：可能会有一些重叠重复，但比丢失数据好
                    merged_text.append(chunk_text)
                    logger.debug(f"块 {i}: 添加文本 (长度 {len(chunk_text)})")

            # 更新时间偏移（减去重叠时间）
            chunk_duration = end_time - start_time
            time_offset += chunk_duration - overlap_seconds

        # 合并文本
        final_text = " ".join(merged_text).strip()

        logger.info(f"合并完成: 共 {len(chunk_results)} 个块")
        logger.info(f"最终文本长度: {len(final_text)} 字符")
        for i, chunk_result in enumerate(chunk_results):
            chunk_text = chunk_result.get("text", "")
            logger.info(f"  块 {i}: {len(chunk_text)} 字符")

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
            "processing_time": total_time,
            "char_timestamps": merged_char_timestamps,
            "vad_segments": merged_vad_segments
        }

        # 跨 chunk 漂移校正
        if len(chunk_results) > 1 and merged_char_timestamps:
            result["char_timestamps"] = self._correct_boundary_drift(
                result["char_timestamps"], chunk_results, overlap_seconds
            )
            result["vad_segments"] = self._correct_vad_drift(
                result["vad_segments"], chunk_results, overlap_seconds
            )

        logger.info(f"合并完成: 总文本长度 {len(final_text)} 字符")
        return result

    def _correct_boundary_drift(
        self,
        char_timestamps: List[dict],
        chunk_results: List[dict],
        overlap_seconds: float,
        threshold: float = 0.3,
    ) -> List[dict]:
        """
        校正跨 chunk 边界处 char_timestamps 的累积漂移。

        检查每个 chunk 边界处实际时间戳与预期边界时间的偏差，
        若偏差超过阈值，对后续所有时间戳做线性校正。
        """
        if not char_timestamps or len(chunk_results) <= 1:
            return char_timestamps

        corrected = list(char_timestamps)

        for boundary_idx in range(len(chunk_results) - 1):
            expected_boundary = chunk_results[boundary_idx].get("end_time", 0.0)

            # 找到该边界附近的最后一个时间戳
            # 在 expected_boundary ± overlap_seconds 范围内查找
            search_start = expected_boundary - overlap_seconds - 1.0
            search_end = expected_boundary + overlap_seconds + 1.0

            boundary_ts = [
                ts for ts in corrected
                if search_start <= ts["start"] <= search_end
            ]
            if not boundary_ts:
                continue

            # 取边界附近时间戳的中位 end 值作为实际边界
            ends = sorted(ts["end"] for ts in boundary_ts)
            observed_boundary = ends[len(ends) // 2]

            drift = observed_boundary - expected_boundary
            if abs(drift) <= threshold:
                continue

            logger.info(f"Chunk 边界 {boundary_idx}->{boundary_idx + 1}: "
                       f"检测到漂移 {drift:.3f}s (阈值 {threshold}s)，校正后续时间戳")

            # 对 expected_boundary 之后的所有时间戳做线性校正
            for j in range(len(corrected)):
                if corrected[j]["start"] >= expected_boundary:
                    corrected[j] = {
                        "word": corrected[j]["word"],
                        "start": round(corrected[j]["start"] - drift, 3),
                        "end": round(corrected[j]["end"] - drift, 3),
                    }

        return corrected

    def _correct_vad_drift(
        self,
        vad_segments: List[dict],
        chunk_results: List[dict],
        overlap_seconds: float,
        threshold: float = 0.3,
    ) -> List[dict]:
        """与 _correct_boundary_drift 相同的逻辑，但应用于 VAD segments。"""
        if not vad_segments or len(chunk_results) <= 1:
            return vad_segments

        corrected = list(vad_segments)

        for boundary_idx in range(len(chunk_results) - 1):
            expected_boundary = chunk_results[boundary_idx].get("end_time", 0.0)

            near_boundary = [
                vs for vs in corrected
                if abs(vs["start_time"] - expected_boundary) <= overlap_seconds + 1.0
            ]
            if not near_boundary:
                continue

            ends = sorted(vs["end_time"] for vs in near_boundary)
            observed_boundary = ends[len(ends) // 2]

            drift = observed_boundary - expected_boundary
            if abs(drift) <= threshold:
                continue

            for j in range(len(corrected)):
                if corrected[j]["start_time"] >= expected_boundary:
                    corrected[j] = {
                        "start_time": round(corrected[j]["start_time"] - drift, 3),
                        "end_time": round(corrected[j]["end_time"] - drift, 3),
                        "text": corrected[j]["text"],
                    }

        return corrected

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


def get_audio_chunker(
    chunk_duration: int = 300,
    overlap: int = 2,
    min_duration: int = 30
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
