"""
语音转文字模块
基于OpenAI Whisper实现高精度语音识别
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
        
        # 模型实例
        self.model = None
        self.model_lock = threading.Lock()
        
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
        加载Whisper模型
        
        Args:
            model_name: 模型名称，None则使用当前设置的模型
        """
        if model_name:
            self.model_name = model_name
        
        with self.model_lock:
            if self.model is not None and hasattr(self.model, 'device'):
                # 如果模型已加载且设备匹配，则跳过
                if str(self.model.device).startswith(self.device):
                    logger.info(f"模型 {self.model_name} 已加载")
                    return
            
            try:
                logger.info(f"正在加载Whisper模型: {self.model_name}")
                
                # 在线程池中加载模型，避免阻塞
                loop = asyncio.get_event_loop()
                self.model = await loop.run_in_executor(
                    None, 
                    self._load_model_sync
                )
                
                logger.info(f"模型加载完成: {self.model_name}")
                
            except Exception as e:
                logger.error(f"模型加载失败: {e}")
                raise Exception(f"Whisper模型加载失败: {str(e)}")
    
    def _load_model_sync(self) -> whisper.Whisper:
        """同步加载模型"""
        # 设置模型下载路径
        os.environ['WHISPER_CACHE_DIR'] = self.model_cache_dir
        
        # 加载模型
        model = whisper.load_model(
            self.model_name.value, 
            device=self.device,
            download_root=self.model_cache_dir
        )
        
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
            
            loop = asyncio.get_event_loop()
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
                segments.append(TranscriptionSegment(
                    start_time=float(segment.get("start", 0)),
                    end_time=float(segment.get("end", 0)),
                    text=segment.get("text", "").strip(),
                    confidence=float(segment.get("avg_logprob", 0.0))
                ))
            
            # 计算整体置信度
            if segments:
                avg_confidence = sum(seg.confidence for seg in segments) / len(segments)
                # 转换为0-1范围的置信度
                confidence = max(0.0, min(1.0, (avg_confidence + 5) / 5))
            else:
                confidence = 0.5  # 默认置信度
            
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


# 全局转录器实例
speech_transcriber = SpeechTranscriber()


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