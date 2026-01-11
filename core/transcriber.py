"""
语音转文字模块
基于OpenAI Whisper实现高精度语音识别
支持重试机制以提高可靠性
"""

import os
import time
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Union

import torch
import whisper
import numpy as np
from loguru import logger

from models.schemas import (
    TranscriptionResult, TranscriptionSegment, WhisperModel,
    Language, OutputFormat
)
from utils.common import retry_on_exception


class SpeechTranscriber:
    """语音转录器"""

    def __init__(
        self,
        model_name: WhisperModel = WhisperModel.SMALL,
        device: Optional[str] = None,
        model_cache_dir: Optional[str] = None
    ):
        """
        初始化转录器

        Args:
            model_name: Whisper模型名称
            device: 计算设备 ('cpu', 'cuda', 'auto')
            model_cache_dir: 模型缓存目录
        """
        self.model_name = model_name
        self.model_cache_dir = model_cache_dir or "./models_cache"

        # 确保缓存目录存在
        Path(self.model_cache_dir).mkdir(parents=True, exist_ok=True)

        # 设置设备
        self.device = self._determine_device(device)
        logger.info(f"使用设备: {self.device}")

        # 模型实例和加载锁
        self.model = None
        self.model_lock = threading.Lock()
        self._model_loaded = False
        
        # 支持的模型信息
        self.model_info = {
            WhisperModel.TINY: {"size": "39MB", "speed": "10x", "accuracy": "★★☆☆☆"},
            WhisperModel.BASE: {"size": "74MB", "speed": "7x", "accuracy": "★★★☆☆"},
            WhisperModel.SMALL: {"size": "244MB", "speed": "4x", "accuracy": "★★★★☆"},
            WhisperModel.MEDIUM: {"size": "769MB", "speed": "2x", "accuracy": "★★★★★"},
            WhisperModel.LARGE: {"size": "1550MB", "speed": "1x", "accuracy": "★★★★★"}
        }
    
    def _determine_device(self, device: Optional[str]) -> str:
        """确定计算设备"""
        if device == "auto" or device is None:
            if torch.cuda.is_available():
                device = "cuda"
                logger.info("检测到CUDA，使用GPU加速")
            else:
                device = "cpu"
                logger.info("未检测到CUDA，使用CPU")
        elif device == "cuda" and not torch.cuda.is_available():
            logger.warning("指定使用CUDA但未检测到，回退到CPU")
            device = "cpu"
        
        return device
    
    async def load_model(self, model_name: Optional[WhisperModel] = None) -> None:
        """
        加载Whisper模型 (线程安全)

        Args:
            model_name: 模型名称，None则使用当前设置的模型
        """
        if model_name:
            self.model_name = model_name

        with self.model_lock:
            # 检查模型是否已加载且匹配
            if self._model_loaded and self.model is not None:
                if str(self.model.device).startswith(self.device):
                    logger.info(f"模型 {self.model_name} 已加载")
                    return

            try:
                logger.info(f"正在加载Whisper模型: {self.model_name}")

                # 在线程池中加载模型，避免阻塞
                loop = asyncio.get_running_loop()
                self.model = await loop.run_in_executor(
                    None,
                    self._load_model_sync
                )
                self._model_loaded = True

                logger.info(f"模型加载完成: {self.model_name}")

            except Exception as e:
                logger.error(f"模型加载失败: {e}")
                raise Exception(f"Whisper模型加载失败: {str(e)}")
    
    def _load_model_sync(self) -> whisper.Whisper:
        """同步加载模型"""
        import time

        # 设置模型下载路径
        os.environ['WHISPER_CACHE_DIR'] = self.model_cache_dir

        # 检查模型是否已缓存
        model_path = os.path.join(self.model_cache_dir, f"{self.model_name.value}.pt")

        if not os.path.exists(model_path):
            logger.info(f"模型文件不存在，将从网络下载: {self.model_name.value}")
            logger.info("支持源: ModelScope(国内), HuggingFace, OpenAI")

            # 使用自定义下载器
            try:
                from utils.model_downloader import download_whisper_model

                def progress_callback(percent):
                    if percent % 20 == 0:  # 每20%显示一次
                        logger.info(f"下载进度: {percent:.0f}%")

                download_whisper_model(
                    model_name=self.model_name.value,
                    cache_dir=self.model_cache_dir,
                    source="auto",
                    progress_callback=progress_callback
                )
                logger.info("模型下载完成")

            except Exception as e:
                logger.warning(f"自定义下载失败，使用默认方式: {e}")
                logger.info("如果网络问题持续，请手动下载模型文件")

        start_time = time.time()

        # 加载模型
        logger.info(f"开始加载模型 {self.model_name.value} 到 {self.device}...")
        model = whisper.load_model(
            self.model_name.value,
            device=self.device,
            download_root=self.model_cache_dir
        )

        load_time = time.time() - start_time
        logger.info(f"模型加载完成 (耗时 {load_time:.2f} 秒)")

        return model
    
    async def transcribe_audio(
        self,
        audio_path: str,
        language: Language = Language.AUTO,
        with_timestamps: bool = False,
        temperature: float = 0.0,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> TranscriptionResult:
        """
        转录音频文件
        
        Args:
            audio_path: 音频文件路径
            language: 目标语言
            with_timestamps: 是否包含时间戳
            temperature: 采样温度
            progress_callback: 进度回调函数
            
        Returns:
            TranscriptionResult: 转录结果
        """
        try:
            logger.info(f"开始转录音频: {audio_path}")
            start_time = time.time()
            
            # 检查文件是否存在
            if not os.path.exists(audio_path):
                raise Exception(f"音频文件不存在: {audio_path}")
            
            # 确保模型已加载
            if self.model is None:
                await self.load_model()
            
            # 准备转录选项
            transcribe_options = {
                "language": language.value if language != Language.AUTO else None,
                "task": "transcribe",
                "temperature": temperature,
                "verbose": False,
            }
            
            # 如果需要时间戳，启用word_timestamps
            if with_timestamps:
                transcribe_options["word_timestamps"] = True
            
            # 执行转录
            if progress_callback:
                progress_callback(10)  # 开始转录

            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                audio_path,
                transcribe_options,
                progress_callback
            )
            
            if progress_callback:
                progress_callback(90)  # 转录完成，开始处理结果
            
            # 处理转录结果
            transcription_result = self._process_transcription_result(
                result, time.time() - start_time
            )
            
            if progress_callback:
                progress_callback(100)  # 完成
            
            logger.info(f"转录完成，耗时: {transcription_result.processing_time:.2f}秒")
            return transcription_result
            
        except Exception as e:
            logger.error(f"音频转录失败: {e}")
            raise Exception(f"音频转录失败: {str(e)}")
    
    def _transcribe_sync(
        self, 
        audio_path: str, 
        options: Dict[str, Any],
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> Dict[str, Any]:
        """同步执行转录"""
        try:
            # 模拟进度更新
            if progress_callback:
                progress_callback(20)
            
            if self.model is None:
                raise Exception("模型未加载，请先调用load_model()")
            
            result = self.model.transcribe(audio_path, **options)
            
            if progress_callback:
                progress_callback(80)
            
            return result
            
        except Exception as e:
            logger.error(f"Whisper转录失败: {e}")
            raise
    
    def _process_transcription_result(
        self,
        whisper_result: Dict[str, Any],
        processing_time: float
    ) -> TranscriptionResult:
        """处理Whisper转录结果"""
        try:
            # 提取基本信息
            text = whisper_result.get("text", "").strip()
            language = whisper_result.get("language", "unknown")

            # 处理片段信息
            segments = []
            whisper_segments = whisper_result.get("segments", [])

            for segment in whisper_segments:
                # 计算片段置信度 (从logprob转换)
                segment_logprob = segment.get("avg_logprob", -5.0)
                segment_confidence = self._logprob_to_confidence(segment_logprob)

                segments.append(TranscriptionSegment(
                    start_time=float(segment.get("start", 0)),
                    end_time=float(segment.get("end", 0)),
                    text=segment.get("text", "").strip(),
                    confidence=segment_confidence
                ))

            # 计算整体置信度 (基于片段的平均置信度)
            if segments:
                confidence = sum(seg.confidence for seg in segments) / len(segments)
            else:
                # 如果没有片段，使用整体结果的no_speech_prob来估算
                no_speech_prob = whisper_result.get("no_speech_prob", 0.0)
                confidence = 1.0 - no_speech_prob

            return TranscriptionResult(
                text=text,
                language=language,
                confidence=confidence,
                segments=segments,
                processing_time=processing_time,
                whisper_model=self.model_name
            )

        except Exception as e:
            logger.error(f"转录结果处理失败: {e}")
            raise Exception(f"转录结果处理失败: {str(e)}")

    def _logprob_to_confidence(self, logprob: float) -> float:
        """
        将 Whisper 的 logprob 转换为 0-1 范围的置信度

        Whisper 的 avg_logprob 典型值范围:
        - -0.5 ~ -1.0: 优秀 (95%+ 置信度)
        - -1.0 ~ -2.0: 良好 (85-95% 置信度)
        - -2.0 ~ -3.0: 一般 (70-85% 置信度)
        - -3.0 ~ -5.0: 较差 (50-70% 置信度)
        - < -5.0: 很差 (<50% 置信度)

        Args:
            logprob: Whisper 的对数概率值

        Returns:
            float: 0-1 范围的置信度
        """
        import math

        # 限制 logprob 范围避免极端值
        logprob = max(-10.0, min(0.0, logprob))

        # 使用分段函数进行转换
        if logprob >= -1.0:
            # 优秀范围: 线性映射到 0.85-1.0
            confidence = 1.0 - (logprob + 0.5) * 0.1
        elif logprob >= -2.0:
            # 良好范围: 线性映射到 0.75-0.85
            confidence = 0.85 - (logprob + 1.0) * 0.1
        elif logprob >= -3.0:
            # 一般范围: 线性映射到 0.60-0.75
            confidence = 0.75 - (logprob + 2.0) * 0.15
        elif logprob >= -5.0:
            # 较差范围: 线性映射到 0.30-0.60
            confidence = 0.60 - (logprob + 3.0) * 0.15
        else:
            # 很差范围: 线性映射到 0.0-0.30
            confidence = max(0.0, 0.30 - (logprob + 5.0) * 0.1)

        return max(0.0, min(1.0, confidence))

    async def transcribe_audio_with_chunking(
        self,
        audio_path: str,
        language: Language = Language.AUTO,
        with_timestamps: bool = False,
        temperature: float = 0.0,
        progress_callback: Optional[Callable[[float], None]] = None,
        enable_chunking: bool = True,
        chunk_duration: int = 180,
        chunk_overlap: int = 2,
        min_chunk_duration: int = 300
    ) -> TranscriptionResult:
        """
        使用分块处理转录音频文件（适用于长音频）

        分块处理可以避免 Whisper 在长音频上的重复/卡顿问题

        Args:
            audio_path: 音频文件路径
            language: 目标语言
            with_timestamps: 是否包含时间戳
            temperature: 采样温度
            progress_callback: 进度回调函数
            enable_chunking: 是否启用分块处理
            chunk_duration: 每块时长（秒）
            chunk_overlap: 块之间重叠时间（秒）
            min_chunk_duration: 启用分块的最小音频时长（秒）

        Returns:
            TranscriptionResult: 转录结果
        """
        from utils.audio import get_audio_chunker

        start_time = time.time()

        # 创建分块器
        chunker = get_audio_chunker(
            chunk_duration=chunk_duration,
            overlap=chunk_overlap,
            min_duration=min_chunk_duration
        )

        # 检查是否需要分块
        if not enable_chunking or not chunker.should_chunk(audio_path):
            # 不需要分块，使用普通转录
            logger.info("音频较短，使用普通转录")
            return await self.transcribe_audio(
                audio_path=audio_path,
                language=language,
                with_timestamps=with_timestamps,
                temperature=temperature,
                progress_callback=progress_callback
            )

        logger.info(f"启用音频分块处理: {audio_path}")

        chunks = []  # 在 try 块外初始化，确保 finally 块可访问
        try:
            # 分割音频
            if progress_callback:
                progress_callback(5)

            chunks = await chunker.split_audio(audio_path)
            total_chunks = len(chunks)

            logger.info(f"音频已分割为 {total_chunks} 块")

            if progress_callback:
                progress_callback(10)

            # 确保模型已加载
            if self.model is None:
                await self.load_model()

            # 转录每个块
            chunk_results = []
            for i, (chunk_path, start_time, end_time) in enumerate(chunks):
                # 计算进度
                base_progress = 10 + (i / total_chunks) * 80

                if progress_callback:
                    progress_callback(base_progress)

                # 转录当前块
                chunk_result = await self._transcribe_audio_sync(
                    chunk_path,
                    language,
                    with_timestamps,
                    temperature
                )

                # 添加时间信息用于合并
                chunk_result["start_time"] = start_time
                chunk_result["end_time"] = end_time

                chunk_results.append(chunk_result)

                logger.debug(f"块 {i + 1}/{total_chunks} 转录完成")

            if progress_callback:
                progress_callback(95)

            # 合并结果
            merged_result = chunker.merge_results(
                chunk_results,
                overlap_seconds=chunk_overlap
            )

            # 转换为 TranscriptionResult
            result = self._dict_to_transcription_result(
                merged_result,
                time.time() - start_time
            )

            if progress_callback:
                progress_callback(100)

            logger.info(f"分块转录完成: {len(result.text)} 字符")
            return result

        except Exception as e:
            logger.error(f"分块转录失败: {e}")
            # 回退到普通转录
            logger.info("回退到普通转录模式")
            try:
                return await self.transcribe_audio(
                    audio_path=audio_path,
                    language=language,
                    with_timestamps=with_timestamps,
                    temperature=temperature,
                    progress_callback=progress_callback
                )
            except Exception as fallback_error:
                logger.error(f"普通转录也失败: {fallback_error}")
                raise
        finally:
            # 确保清理临时文件
            if chunks:
                try:
                    await chunker.cleanup_chunks([c[0] for c in chunks])
                except Exception as cleanup_error:
                    logger.warning(f"清理临时文件失败: {cleanup_error}")

    def _dict_to_transcription_result(
        self,
        result_dict: dict,
        processing_time: float
    ) -> TranscriptionResult:
        """将字典结果转换为 TranscriptionResult 对象"""
        segments = []
        for seg in result_dict.get("segments", []):
            segments.append(TranscriptionSegment(
                start_time=float(seg.get("start", 0)),
                end_time=float(seg.get("end", 0)),
                text=seg.get("text", "").strip(),
                confidence=float(seg.get("confidence", result_dict.get("confidence", 0.5)))
            ))

        return TranscriptionResult(
            text=result_dict.get("text", "").strip(),
            language=result_dict.get("language", "unknown"),
            confidence=float(result_dict.get("confidence", 0.5)),
            segments=segments,
            processing_time=processing_time,
            whisper_model=self.model_name
        )

    async def _transcribe_audio_sync(
        self,
        audio_path: str,
        language: Language,
        with_timestamps: bool,
        temperature: float
    ) -> dict:
        """同步转录音频（返回字典格式，带重试机制）"""
        # 准备转录选项
        transcribe_options = {
            "language": language.value if language != Language.AUTO else None,
            "task": "transcribe",
            "temperature": temperature,
            "verbose": False,
        }

        # 如果需要时间戳，启用word_timestamps
        if with_timestamps:
            transcribe_options["word_timestamps"] = True

        # 使用带重试的转录
        result = await self._sync_transcribe_with_retry(
            audio_path=audio_path,
            options=transcribe_options,
            max_retries=2,
            retry_delay=2.0
        )

        # 处理结果
        return self._process_whisper_result_to_dict(result)

    def _process_whisper_result_to_dict(self, whisper_result: dict) -> dict:
        """将 Whisper 结果转换为字典格式"""
        text = whisper_result.get("text", "").strip()
        language = whisper_result.get("language", "unknown")

        # 处理片段
        segments = []
        whisper_segments = whisper_result.get("segments", [])

        for segment in whisper_segments:
            segment_logprob = segment.get("avg_logprob", -5.0)
            segment_confidence = self._logprob_to_confidence(segment_logprob)

            segments.append({
                "start": float(segment.get("start", 0)),
                "end": float(segment.get("end", 0)),
                "text": segment.get("text", "").strip(),
                "confidence": segment_confidence
            })

        # 计算整体置信度
        if segments:
            avg_confidence = sum(s["confidence"] for s in segments) / len(segments)
            confidence = avg_confidence
        else:
            # 使用 no_speech_prob
            no_speech_prob = whisper_result.get("no_speech_prob", 0.0)
            confidence = 1.0 - no_speech_prob

        return {
            "text": text,
            "segments": segments,
            "language": language,
            "confidence": confidence
        }

    async def _sync_transcribe_with_retry(
        self,
        audio_path: str,
        options: dict,
        max_retries: int = 2,
        retry_delay: float = 2.0
    ) -> dict:
        """
        带重试机制的同步 Whisper 转录

        Args:
            audio_path: 音频文件路径
            options: Whisper 转录选项
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）

        Returns:
            dict: Whisper 转录结果
        """
        # 定义可能需要重试的异常类型
        retryable_exceptions = (
            RuntimeError,  # CUDA OOM 等
            OSError,  # 文件读取错误
            TimeoutError,  # 超时
            ConnectionError,  # 连接错误
        )

        @retry_on_exception(
            max_retries=max_retries,
            delay=retry_delay,
            backoff=2.0,
            exceptions=retryable_exceptions
        )
        async def _transcribe():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                self._sync_transcribe,
                audio_path,
                options
            )

        try:
            return await _transcribe()
        except Exception as e:
            # 如果重试后仍然失败，记录并抛出
            logger.error(f"Whisper 转录失败（已重试 {max_retries} 次）: {e}")
            raise

    def _sync_transcribe(self, audio_path: str, options: dict) -> dict:
        """同步执行 Whisper 转录（不带重试）"""
        return self.model.transcribe(audio_path, **options)

    async def transcribe_batch(
        self,
        audio_paths: List[str],
        language: Language = Language.AUTO,
        max_concurrent: int = 3,
        progress_callback: Optional[Callable[[str, float], None]] = None
    ) -> List[TranscriptionResult]:
        """
        批量转录音频文件
        
        Args:
            audio_paths: 音频文件路径列表
            language: 目标语言
            max_concurrent: 最大并发数
            progress_callback: 进度回调函数 (文件路径, 进度)
            
        Returns:
            List[TranscriptionResult]: 转录结果列表
        """
        try:
            logger.info(f"开始批量转录 {len(audio_paths)} 个文件")
            
            # 确保模型已加载
            if self.model is None:
                await self.load_model()
            
            # 创建信号量限制并发数
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def transcribe_single(audio_path: str) -> TranscriptionResult:
                async with semaphore:
                    def single_progress(progress: float):
                        if progress_callback:
                            progress_callback(audio_path, progress)
                    
                    return await self.transcribe_audio(
                        audio_path=audio_path,
                        language=language,
                        progress_callback=single_progress
                    )
            
            # 并发执行转录任务
            tasks = [transcribe_single(path) for path in audio_paths]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果，将异常转换为错误结果
            processed_results = []
            for i, result in enumerate(results):
                if isinstance(result, Exception):
                    logger.error(f"文件 {audio_paths[i]} 转录失败: {result}")
                    # 创建错误结果
                    error_result = TranscriptionResult(
                        text=f"转录失败: {str(result)}",
                        language="unknown",
                        confidence=0.0,
                        segments=[],
                        processing_time=0.0,
                        whisper_model=self.model_name
                    )
                    processed_results.append(error_result)
                else:
                    processed_results.append(result)
            
            logger.info(f"批量转录完成，成功: {len([r for r in results if not isinstance(r, Exception)])}")
            return processed_results
            
        except Exception as e:
            logger.error(f"批量转录失败: {e}")
            raise Exception(f"批量转录失败: {str(e)}")
    
    def format_output(
        self, 
        result: TranscriptionResult, 
        format_type: OutputFormat = OutputFormat.JSON
    ) -> str:
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
                return self._format_srt(result)
            elif format_type == OutputFormat.VTT:
                return self._format_vtt(result)
            else:  # JSON
                return result.model_dump_json(indent=2)
                
        except Exception as e:
            logger.error(f"输出格式化失败: {e}")
            return result.text  # 回退到纯文本
    
    def _format_srt(self, result: TranscriptionResult) -> str:
        """格式化为SRT字幕格式"""
        srt_content = []
        
        for i, segment in enumerate(result.segments, 1):
            start_time = self._seconds_to_srt_time(segment.start_time)
            end_time = self._seconds_to_srt_time(segment.end_time)
            
            srt_content.append(f"{i}")
            srt_content.append(f"{start_time} --> {end_time}")
            srt_content.append(segment.text)
            srt_content.append("")  # 空行
        
        return "\n".join(srt_content)
    
    def _format_vtt(self, result: TranscriptionResult) -> str:
        """格式化为VTT字幕格式"""
        vtt_content = ["WEBVTT", ""]
        
        for segment in result.segments:
            start_time = self._seconds_to_vtt_time(segment.start_time)
            end_time = self._seconds_to_vtt_time(segment.end_time)
            
            vtt_content.append(f"{start_time} --> {end_time}")
            vtt_content.append(segment.text)
            vtt_content.append("")  # 空行
        
        return "\n".join(vtt_content)
    
    def _seconds_to_srt_time(self, seconds: float) -> str:
        """转换秒数为SRT时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millisecs = int((seconds % 1) * 1000)
        
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millisecs:03d}"
    
    def _seconds_to_vtt_time(self, seconds: float) -> str:
        """转换秒数为VTT时间格式"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"
    
    def get_model_info(self) -> Dict[str, Any]:
        """获取当前模型信息"""
        return {
            "name": self.model_name.value,
            "device": self.device,
            "info": self.model_info.get(self.model_name, {}),
            "loaded": self.model is not None,
            "cache_dir": self.model_cache_dir
        }
    
    def get_available_models(self) -> Dict[str, Dict[str, str]]:
        """获取可用模型列表"""
        return {model.value: info for model, info in self.model_info.items()}
    
    async def unload_model(self) -> None:
        """卸载模型以释放内存"""
        with self.model_lock:
            if self.model is not None:
                del self.model
                self.model = None
                self._model_loaded = False

                # 清理GPU内存
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                logger.info("模型已卸载")
    
    def __del__(self):
        """析构函数"""
        try:
            if self.model is not None:
                del self.model
        except Exception:
            pass


# 全局转录器实例 (用于简单的单任务场景)
speech_transcriber = SpeechTranscriber()


def create_transcriber(
    model_name: WhisperModel = WhisperModel.SMALL,
    device: Optional[str] = None,
    model_cache_dir: Optional[str] = None
) -> SpeechTranscriber:
    """
    创建新的转录器实例 (线程安全)

    每个请求应创建独立的转录器实例，避免全局单例的竞态条件。

    Args:
        model_name: Whisper模型名称
        device: 计算设备 ('cpu', 'cuda', 'auto')
        model_cache_dir: 模型缓存目录

    Returns:
        SpeechTranscriber: 新的转录器实例
    """
    return SpeechTranscriber(
        model_name=model_name,
        device=device,
        model_cache_dir=model_cache_dir
    )


async def transcribe_audio_file(
    audio_path: str,
    model: WhisperModel = WhisperModel.SMALL,
    language: Language = Language.AUTO,
    with_timestamps: bool = False,
    output_format: OutputFormat = OutputFormat.JSON,
    progress_callback: Optional[Callable[[float], None]] = None
) -> Union[TranscriptionResult, str]:
    """
    转录音频文件的便捷函数
    
    Args:
        audio_path: 音频文件路径
        model: Whisper模型
        language: 语言
        with_timestamps: 是否包含时间戳
        output_format: 输出格式
        progress_callback: 进度回调
        
    Returns:
        TranscriptionResult或格式化的字符串
    """
    # 如果需要不同的模型，重新初始化转录器
    if speech_transcriber.model_name != model:
        speech_transcriber.model_name = model
        speech_transcriber.model = None  # 强制重新加载
    
    # 执行转录
    result = await speech_transcriber.transcribe_audio(
        audio_path=audio_path,
        language=language,
        with_timestamps=with_timestamps,
        progress_callback=progress_callback
    )
    
    # 根据输出格式返回结果
    if output_format == OutputFormat.JSON:
        return result
    else:
        return speech_transcriber.format_output(result, output_format)


if __name__ == "__main__":
    # 测试代码
    import asyncio
    
    async def test():
        transcriber = SpeechTranscriber(WhisperModel.TINY)
        
        try:
            print("测试转录器初始化...")
            print(f"模型信息: {transcriber.get_model_info()}")
            print(f"可用模型: {transcriber.get_available_models()}")
            
            # 加载模型测试
            await transcriber.load_model()
            print("模型加载测试完成")
            
            # 卸载模型测试
            await transcriber.unload_model()
            print("模型卸载测试完成")
            
        except Exception as e:
            print(f"测试失败: {e}")
    
    # asyncio.run(test())