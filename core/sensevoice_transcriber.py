"""
SenseVoice 语音转录器
基于阿里巴巴达摩院的 SenseVoice 模型
支持多语言语音识别，对中文等亚洲语言效果更佳
"""

import os
import time
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable

import torch
import numpy as np
from loguru import logger

try:
    from funasr import AutoModel
    from funasr.utils.postprocess_utils import rich_transcription_postprocess
    FUNASR_AVAILABLE = True
except ImportError:
    FUNASR_AVAILABLE = False
    logger.warning("funasr 未安装，SenseVoice 功能不可用")

from models.schemas import (
    TranscriptionResult,
    TranscriptionSegment,
    Language,
    OutputFormat
)


class SenseVoiceTranscriber:
    """SenseVoice 语音转录器"""

    # 支持的模型配置
    MODEL_CONFIGS = {
        "sensevoice-small": {
            "repo": "iic/SenseVoiceSmall",
            "name": "SenseVoice Small",
            "size": "244MB",
            "description": "多语言语音识别，中文优化",
            "languages": ["zh", "en", "yue", "ja", "ko", "nospeech"],
        }
    }

    def __init__(
        self,
        model_name: str = "sensevoice-small",
        device: Optional[str] = None,
        model_cache_dir: Optional[str] = None,
        language: str = "auto"
    ):
        """
        初始化 SenseVoice 转录器

        Args:
            model_name: 模型名称
            device: 计算设备 ('cpu', 'cuda', 'auto')
            model_cache_dir: 模型缓存目录
            language: 默认语言 ('auto', 'zh', 'en', 'yue', 'ja', 'ko')
        """
        if not FUNASR_AVAILABLE:
            raise RuntimeError(
                "SenseVoice 需要 funasr 库。请运行: pip install funasr modelscope"
            )

        self.model_name = model_name
        self.model_cache_dir = model_cache_dir or "./models_cache"
        self.default_language = language

        # 确保缓存目录存在
        Path(self.model_cache_dir).mkdir(parents=True, exist_ok=True)

        # 设置设备
        self.device = self._determine_device(device)
        logger.info(f"SenseVoice 使用设备: {self.device}")

        # 模型实例和加载锁
        self.model = None
        self.model_lock = threading.Lock()
        self._model_loaded = False

        # 语言映射
        self.language_map = {
            "auto": "auto",
            "zh": "zh",
            "en": "en",
            "yue": "yue",  # 粤语
            "ja": "ja",   # 日语
            "ko": "ko",   # 韩语
        }

    def _determine_device(self, device: Optional[str]) -> str:
        """确定计算设备"""
        if device == "auto" or device is None:
            if torch.cuda.is_available():
                device = "cuda"
                logger.info("检测到CUDA，SenseVoice 使用GPU加速")
            else:
                device = "cpu"
                logger.info("未检测到CUDA，SenseVoice 使用CPU")
        elif device == "cuda" and not torch.cuda.is_available():
            logger.warning("指定使用CUDA但未检测到，回退到CPU")
            device = "cpu"

        return device

    async def load_model(self, model_name: Optional[str] = None) -> None:
        """
        加载 SenseVoice 模型 (线程安全)

        Args:
            model_name: 模型名称，None则使用当前设置的模型
        """
        if model_name:
            self.model_name = model_name

        with self.model_lock:
            if self._model_loaded and self.model is not None:
                logger.info(f"SenseVoice 模型 {self.model_name} 已加载")
                return

            try:
                logger.info(f"正在加载 SenseVoice 模型: {self.model_name}")

                loop = asyncio.get_running_loop()
                self.model = await loop.run_in_executor(
                    None,
                    self._load_model_sync
                )
                self._model_loaded = True

                logger.info(f"SenseVoice 模型加载完成: {self.model_name}")

            except Exception as e:
                logger.error(f"SenseVoice 模型加载失败: {e}")
                raise Exception(f"SenseVoice 模型加载失败: {str(e)}")

    def _load_model_sync(self) -> Any:
        """同步加载模型"""
        import time

        config = self.MODEL_CONFIGS.get(self.model_name)
        if not config:
            raise ValueError(f"不支持的模型: {self.model_name}")

        model_path = config["repo"]
        logger.info(f"从 ModelScope 加载模型: {model_path}")

        start_time = time.time()

        # 使用 funasr 加载模型
        self.model = AutoModel(
            model=model_path,
            device=self.device,
            disable_pbar=False,
            disable_log=False,
        )

        load_time = time.time() - start_time
        logger.info(f"SenseVoice 模型加载完成 (耗时 {load_time:.2f} 秒)")

        return self.model

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
            temperature: 采样温度 (SenseVoice 忽略此参数)
            progress_callback: 进度回调函数

        Returns:
            TranscriptionResult: 转录结果
        """
        try:
            logger.info(f"开始使用 SenseVoice 转录音频: {audio_path}")
            start_time = time.time()

            # 检查文件是否存在
            if not os.path.exists(audio_path):
                raise Exception(f"音频文件不存在: {audio_path}")

            # 确保模型已加载
            if self.model is None:
                await self.load_model()

            if progress_callback:
                progress_callback(10)

            # 准备语言参数
            lang = self._map_language(language)

            # 执行转录
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                audio_path,
                lang,
                with_timestamps,
                progress_callback
            )

            if progress_callback:
                progress_callback(100)

            processing_time = time.time() - start_time
            logger.info(f"SenseVoice 转录完成，耗时: {processing_time:.2f}秒")

            return result

        except Exception as e:
            logger.error(f"SenseVoice 转录失败: {e}")
            raise Exception(f"SenseVoice 转录失败: {str(e)}")

    def _map_language(self, language: Language) -> str:
        """映射语言代码到 SenseVoice 格式"""
        if language == Language.AUTO:
            return "auto"
        lang_map = {
            Language.ZH: "zh",
            Language.EN: "en",
            Language.JA: "ja",
            Language.KO: "ko",
        }
        return lang_map.get(language, "auto")

    def _transcribe_sync(
        self,
        audio_path: str,
        language: str,
        with_timestamps: bool,
        progress_callback: Optional[Callable[[float]], None] = None
    ) -> TranscriptionResult:
        """同步执行转录"""
        try:
            if progress_callback:
                progress_callback(20)

            if self.model is None:
                raise Exception("模型未加载，请先调用load_model()")

            # SenseVoice 推理参数
            rec_config_kwargs = {
                "batch_size_s": 300,  # 静音切断
                "merge_vad": True,    # 合并 vad
                "merge_length_s": 5,  # 合并长度
            }

            # 语言检测参数
            if language != "auto":
                rec_config_kwargs["language"] = language
            else:
                rec_config_kwargs["language"] = "auto"  # 自动检测语言

            # 执行推理
            result = self.model.generate(
                input=audio_path,
                cache_path=self.model_cache_dir,
                **rec_config_kwargs
            )

            if progress_callback:
                progress_callback(80)

            # 处理结果
            if len(result) == 0 or len(result[0]) == 0:
                return TranscriptionResult(
                    text="",
                    language=language if language != "auto" else "unknown",
                    confidence=0.0,
                    segments=[],
                    processing_time=0.0,
                    whisper_model=self.model_name
                )

            # 提取转录文本和时间戳
            text = ""
            segments = []
            detected_lang = language if language != "auto" else "zh"

            # SenseVoice 返回格式: [dict with 'sentence', 'timestamp', etc.]
            for item in result[0]:
                # 获取句子文本
                sentence = item.get("sentence", "")
                text += sentence

                # 获取时间戳
                timestamp = item.get("timestamp", [])
                if len(timestamp) >= 2:
                    start_time = timestamp[0] / 1000.0  # 转换为秒
                    end_time = timestamp[1] / 1000.0
                else:
                    start_time = 0.0
                    end_time = 0.0

                # 获取语言（如果有）
                item_lang = item.get("language", detected_lang)

                # 计算置信度（SenseVoice 不直接提供，使用默认值）
                confidence = 0.95

                segments.append(TranscriptionSegment(
                    start_time=start_time,
                    end_time=end_time,
                    text=sentence.strip(),
                    confidence=confidence
                ))

                # 更新检测到的语言
                if "language" in item:
                    detected_lang = item["language"]

            # 计算整体置信度
            if segments:
                avg_confidence = sum(seg.confidence for seg in segments) / len(segments)
                confidence = avg_confidence
            else:
                confidence = 0.95  # 默认置信度

            return TranscriptionResult(
                text=text.strip(),
                language=detected_lang,
                confidence=confidence,
                segments=segments,
                processing_time=0.0,  # 将在调用处设置
                whisper_model=self.model_name
            )

        except Exception as e:
            logger.error(f"SenseVoice 推理失败: {e}")
            raise

    def get_model_info(self) -> Dict[str, Any]:
        """获取当前模型信息"""
        config = self.MODEL_CONFIGS.get(self.model_name, {})
        return {
            "name": self.model_name,
            "device": self.device,
            "type": "SenseVoice",
            "info": config,
            "loaded": self.model is not None,
            "cache_dir": self.model_cache_dir
        }

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

                logger.info("SenseVoice 模型已卸载")


def create_sensevoice_transcriber(
    model_name: str = "sensevoice-small",
    device: Optional[str] = None,
    model_cache_dir: Optional[str] = None,
    language: str = "auto"
) -> SenseVoiceTranscriber:
    """
    创建 SenseVoice 转录器实例

    Args:
        model_name: 模型名称
        device: 计算设备 ('cpu', 'cuda', 'auto')
        model_cache_dir: 模型缓存目录
        language: 默认语言

    Returns:
        SenseVoiceTranscriber: SenseVoice 转录器实例
    """
    return SenseVoiceTranscriber(
        model_name=model_name,
        device=device,
        model_cache_dir=model_cache_dir,
        language=language
    )


if __name__ == "__main__":
    # 测试代码
    import asyncio

    async def test():
        try:
            print("测试 SenseVoice 转录器...")

            transcriber = create_sensevoice_transcriber()

            print(f"模型信息: {transcriber.get_model_info()}")

            # 加载模型测试
            await transcriber.load_model()
            print("SenseVoice 模型加载测试完成")

            # 卸载模型测试
            await transcriber.unload_model()
            print("SenseVoice 模型卸载测试完成")

        except Exception as e:
            print(f"测试失败: {e}")

    asyncio.run(test())
