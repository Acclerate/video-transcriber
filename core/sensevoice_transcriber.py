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
    FUNASR_AVAILABLE = True
    PUNCTUATION_AVAILABLE = True
except ImportError:
    FUNASR_AVAILABLE = False
    PUNCTUATION_AVAILABLE = False
    logger.warning("funasr 未安装，SenseVoice 功能不可用")

from models.schemas import (
    TranscriptionResult,
    TranscriptionSegment,
    Language,
    OutputFormat
)

# 导入音频分块处理模块
try:
    from utils.audio.chunking import AudioChunker, get_audio_chunker
    CHUNKING_AVAILABLE = True
except ImportError:
    CHUNKING_AVAILABLE = False
    AudioChunker = None
    logger.warning("音频分块模块不可用，长音频处理可能会遇到显存不足问题")


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
        language: str = "auto",
        enable_punctuation: bool = True,
        clean_special_tokens: bool = True,
        enable_chunking: bool = True,
        chunk_duration_seconds: int = 180,
        chunk_overlap_seconds: int = 2,
        min_duration_for_chunking: int = 300
    ):
        """
        初始化 SenseVoice 转录器

        Args:
            model_name: 模型名称
            device: 计算设备 ('cpu', 'cuda', 'auto')
            model_cache_dir: 模型缓存目录
            language: 默认语言 ('auto', 'zh', 'en', 'yue', 'ja', 'ko')
            enable_punctuation: 是否添加标点符号
            clean_special_tokens: 是否清理特殊标记（如 <|zh|><|NEUTRAL|> 等）
            enable_chunking: 是否启用音频分块处理（推荐用于长音频）
            chunk_duration_seconds: 每块时长（秒），默认180秒（3分钟）
            chunk_overlap_seconds: 块之间重叠时间（秒），默认2秒
            min_duration_for_chunking: 超过此时长（秒）才启用分块，默认300秒（5分钟）
        """
        if not FUNASR_AVAILABLE:
            raise RuntimeError(
                "SenseVoice 需要 funasr 库。请运行: pip install funasr modelscope"
            )

        self.model_name = model_name
        self.model_cache_dir = model_cache_dir or "./models_cache"
        self.default_language = language
        self.enable_punctuation = enable_punctuation
        self.clean_special_tokens = clean_special_tokens

        # 音频分块处理配置
        self.enable_chunking = enable_chunking and CHUNKING_AVAILABLE
        self.chunk_duration_seconds = chunk_duration_seconds
        self.chunk_overlap_seconds = chunk_overlap_seconds
        self.min_duration_for_chunking = min_duration_for_chunking

        # 初始化音频分块器
        self.audio_chunker = None
        if self.enable_chunking:
            try:
                self.audio_chunker = get_audio_chunker(
                    chunk_duration=chunk_duration_seconds,
                    overlap=chunk_overlap_seconds,
                    min_duration=min_duration_for_chunking
                )
                logger.info(f"音频分块处理已启用: chunk_duration={chunk_duration_seconds}s, "
                           f"overlap={chunk_overlap_seconds}s, min_duration={min_duration_for_chunking}s")
            except Exception as e:
                logger.warning(f"音频分块器初始化失败: {e}，将禁用分块处理")
                self.enable_chunking = False

        # 确保缓存目录存在
        Path(self.model_cache_dir).mkdir(parents=True, exist_ok=True)

        # 设置设备
        self.device = self._determine_device(device)
        logger.info(f"SenseVoice 使用设备: {self.device}")

        # 模型实例和加载锁
        self.model = None
        self.punctuation_model = None
        self.model_lock = threading.Lock()
        self._model_loaded = False
        self._punctuation_loaded = False

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
        import os

        config = self.MODEL_CONFIGS.get(self.model_name)
        if not config:
            raise ValueError(f"不支持的模型: {self.model_name}")

        model_path = config["repo"]
        logger.info(f"从 ModelScope 加载模型: {model_path}")
        logger.info(f"模型缓存目录: {self.model_cache_dir}")

        # 设置 ModelScope 缓存目录环境变量
        os.environ['MODELSCOPE_CACHE'] = self.model_cache_dir
        # 确保缓存目录存在
        from pathlib import Path
        Path(self.model_cache_dir).mkdir(parents=True, exist_ok=True)

        start_time = time.time()

        # 使用 funasr 加载模型
        self.model = AutoModel(
            model=model_path,
            device=self.device,
            cache_dir=self.model_cache_dir,  # 明确指定缓存目录
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

    def _clean_special_tokens(self, text: str) -> str:
        """
        清理SenseVoice输出的特殊标记

        清理的标记包括：
        - 语言标记: <|zh|>, <|en|>, <|ja|>, <|ko|>, <|yue|>
        - 情感标记: <|NEUTRAL|>, <|HAPPY|>, <|SAD|>, <|ANGRY|>, <|EMO_UNKNOWN|>
        - 事件标记: <|Speech|>, <|Music|>, <|BGM|>
        - 其他特殊标记: <|woitn|> 等

        Args:
            text: 原始文本

        Returns:
            清理后的文本
        """
        import re

        if not text or not self.clean_special_tokens:
            return text

        # 定义所有需要清理的特殊标记模式
        # 格式: <|标记内容|>
        patterns = [
            # 语言标记
            r'<\|(zh|en|ja|ko|yue|nospeech)\|>',
            # 情感标记
            r'<\|(NEUTRAL|HAPPY|SAD|ANGRY|EMO_UNKNOWN)\|>',
            # 事件标记
            r'<\|(Speech|Music|BGM)\|>',
            # 其他可能的特殊标记（通用模式）
            r'<\|[A-Za-z_]+\|>',
        ]

        cleaned_text = text
        for pattern in patterns:
            cleaned_text = re.sub(pattern, '', cleaned_text)

        # 清理多余的空白字符
        cleaned_text = re.sub(r'\s+', ' ', cleaned_text)
        cleaned_text = cleaned_text.strip()

        if cleaned_text != text:
            logger.info(f"特殊标记已清理: 原始长度={len(text)}, 清理后长度={len(cleaned_text)}")

        return cleaned_text

    async def _load_punctuation_model(self) -> None:
        """加载标点符号模型"""
        if not PUNCTUATION_AVAILABLE or not self.enable_punctuation:
            return

        if self._punctuation_loaded and self.punctuation_model is not None:
            return

        try:
            logger.info("正在加载标点符号模型...")
            loop = asyncio.get_running_loop()
            self.punctuation_model = await loop.run_in_executor(
                None,
                self._load_punctuation_sync
            )
            self._punctuation_loaded = True
            logger.info("标点符号模型加载完成")
        except Exception as e:
            logger.warning(f"标点符号模型加载失败: {e}，将跳过标点符号处理")
            self.punctuation_model = None

    def _load_punctuation_sync(self) -> Any:
        """同步加载标点符号模型"""
        # 使用正确的 ModelScope 标点符号模型
        punct_model_paths = [
            "damo/punc_ct-transformer_zh-cn-common-vocab272727-pytorch",  # 官方中文标点符号模型
            "damo/punc_ct-transformer_zh-cn-common-vad_realtime-vocab272727",  # 实时版本
        ]

        for model_path in punct_model_paths:
            try:
                logger.info(f"尝试加载标点符号模型: {model_path}")
                model = AutoModel(
                    model=model_path,
                    device=self.device,
                    cache_dir=self.model_cache_dir,
                    disable_pbar=False,
                    disable_log=False,
                )
                logger.info(f"标点符号模型加载成功: {model_path}")
                return model
            except Exception as e:
                logger.warning(f"加载 {model_path} 失败: {e}")
                continue

        logger.error("所有标点符号模型路径均加载失败")
        return None

    def _add_punctuation(self, text: str, lang: str = "zh") -> str:
        """
        使用标点符号模型添加标点符号

        Args:
            text: 原始文本
            lang: 语言代码

        Returns:
            添加标点符号后的文本
        """
        if not text or not self.enable_punctuation:
            logger.debug(f"跳过标点符号处理: text={bool(text)}, enable_punctuation={self.enable_punctuation}")
            return text

        logger.info(f"开始标点符号处理，文本长度: {len(text)}")

        # 检查模型是否已加载
        if self.punctuation_model is None:
            logger.info("标点符号模型未加载，正在加载...")
            # 如果模型未加载，尝试加载
            try:
                self.punctuation_model = self._load_punctuation_sync()
                if self.punctuation_model:
                    self._punctuation_loaded = True
                    logger.info("标点符号模型加载成功")
                else:
                    logger.warning("标点符号模型加载失败，返回 None")
                    return text
            except Exception as e:
                logger.error(f"标点符号模型加载异常: {e}")
                import traceback
                logger.error(traceback.format_exc())
                return text

        if self.punctuation_model is None:
            logger.warning("标点符号模型仍为 None，跳过处理")
            return text

        try:
            logger.info(f"正在调用标点符号模型处理文本 (前100字符): {text[:100]}...")
            result = self.punctuation_model.generate(
                input=text,
                batch_size_s=300,
            )
            logger.info(f"标点符号模型返回结果类型: {type(result)}, 长度: {len(result) if hasattr(result, '__len__') else 'N/A'}")

            if result and len(result) > 0:
                # 提取处理后的文本
                punct_text = self._extract_punctuation_text(result)
                if punct_text:
                    logger.info(f"标点符号添加成功: 原始长度={len(text)}, 处理后长度={len(punct_text)}")
                    logger.info(f"处理结果预览: {punct_text[:200]}...")
                    return punct_text
                else:
                    logger.warning("无法从标点符号模型结果中提取文本")
            else:
                logger.warning("标点符号模型返回空结果")

            return text
        except Exception as e:
            logger.error(f"标点符号处理失败: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return text

    def _extract_punctuation_text(self, result) -> str:
        """从标点符号模型结果中提取文本"""
        try:
            logger.info(f"提取标点符号文本，结果类型: {type(result)}")

            if isinstance(result, list) and len(result) > 0:
                first_result = result[0]
                logger.info(f"result[0] 类型: {type(first_result)}")

                if isinstance(first_result, list) and len(first_result) > 0:
                    # 可能是字符串列表
                    if isinstance(first_result[0], str):
                        text = ''.join(first_result)
                        logger.info(f"从字符串列表提取文本: {len(text)} 字符")
                        return text
                    # 可能是字典列表
                    elif isinstance(first_result[0], dict):
                        texts = []
                        for item in first_result:
                            text = item.get("text", "")
                            if text:
                                texts.append(text)
                        combined = ''.join(texts)
                        logger.info(f"从字典列表提取文本: {len(combined)} 字符")
                        return combined
                elif isinstance(first_result, str):
                    logger.info(f"从字符串提取文本: {len(first_result)} 字符")
                    return first_result
                elif isinstance(first_result, dict):
                    text = first_result.get("text", str(first_result))
                    logger.info(f"从字典提取文本: {len(text)} 字符")
                    return text
                else:
                    logger.info(f"其他类型，直接转换: {type(first_result)}")
                    return str(first_result)

            logger.info(f"结果不是列表或为空，直接转换为字符串")
            return str(result)
        except Exception as e:
            logger.warning(f"提取标点符号文本失败: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return ""

    def _transcribe_sync(
        self,
        audio_path: str,
        language: str,
        with_timestamps: bool,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> TranscriptionResult:
        """同步执行转录"""
        import time
        start_time = time.time()

        try:
            if progress_callback:
                progress_callback(20)

            if self.model is None:
                raise Exception("模型未加载，请先调用load_model()")

            # 验证音频文件
            import os
            if not os.path.exists(audio_path):
                raise Exception(f"音频文件不存在: {audio_path}")

            file_size = os.path.getsize(audio_path)
            if file_size == 0:
                raise Exception(f"音频文件为空: {audio_path}")

            logger.info(f"音频文件验证通过: {audio_path}, 大小: {file_size} 字节")

            # 转换 language 枚举为字符串
            if hasattr(language, 'value'):
                language_str = language.value
            else:
                language_str = str(language)

            logger.info(f"开始 SenseVoice 转录: {audio_path}")
            logger.info(f"语言模式: {language_str}, 时间戳: {with_timestamps}")

            # ========== 音频分块处理 ==========
            # 检查是否需要对音频进行分块处理
            should_chunk = False
            if self.enable_chunking and self.audio_chunker:
                should_chunk = self.audio_chunker.should_chunk(audio_path)
                audio_duration = self.audio_chunker.get_audio_duration(audio_path)

                if should_chunk:
                    logger.info(f"音频时长 {audio_duration:.1f}s 超过阈值 {self.min_duration_for_chunking}s，"
                               f"将启用分块处理（每块 {self.chunk_duration_seconds}s）")
                    return asyncio.run(self._transcribe_with_chunking(
                        audio_path, language_str, with_timestamps, progress_callback, start_time
                    ))
                else:
                    logger.info(f"音频时长 {audio_duration:.1f}s 不需要分块处理")
            # ========== 音频分块处理结束 ==========

            # SenseVoice 推理参数
            rec_config_kwargs = {
                "batch_size_s": 300,  # 静音切断
                "merge_vad": True,    # 合并 vad
                "merge_length_s": 5,  # 合并长度
            }

            # 语言检测参数
            if language_str != "auto":
                rec_config_kwargs["language"] = language_str
            else:
                rec_config_kwargs["language"] = "auto"  # 自动检测语言

            # 执行推理
            logger.info("正在执行 SenseVoice 推理...")
            logger.info(f"推理参数: batch_size_s=300, merge_vad=True, merge_length_s=5, language={language_str}")
            inference_start = time.time()

            try:
                result = self.model.generate(
                    input=audio_path,
                    cache_path=self.model_cache_dir,
                    **rec_config_kwargs
                )
            except Exception as inference_error:
                logger.error(f"SenseVoice model.generate() 抛出异常: {type(inference_error).__name__}: {inference_error}")
                import traceback
                logger.error(f"推理异常堆栈:\n{traceback.format_exc()}")
                raise Exception(f"SenseVoice 推理异常: {str(inference_error)}")

            inference_time = time.time() - inference_start
            logger.info(f"SenseVoice 推理完成 (耗时 {inference_time:.2f} 秒)")

            # 调试：打印结果结构
            logger.info(f"========== SenseVoice 结果调试信息 ==========")
            logger.info(f"结果类型: {type(result)}")
            logger.info(f"结果类型名称: {type(result).__name__}")
            logger.info(f"结果模块: {type(result).__module__}")
            logger.info(f"结果内容: {repr(result)[:1000]}")  # 打印结果的字符串表示，限制长度

            # 检查结果的所有属性
            if hasattr(result, '__dict__'):
                logger.info(f"结果属性: {result.__dict__}")

            # 如果是列表，打印每个元素的类型
            if hasattr(result, '__len__') and len(result) > 0:
                logger.info(f"结果是一个可迭代对象，长度: {len(result)}")
                for i, item in enumerate(result[:5]):  # 只打印前5个元素
                    logger.info(f"  result[{i}] 类型: {type(item)}, 内容: {repr(item)[:200]}")
            logger.info(f"==========================================")

            # 检查结果是否为空
            if result is None:
                logger.error("SenseVoice 返回 None")
                return TranscriptionResult(
                    text="",
                    language=language_str,
                    confidence=0.0,
                    segments=[],
                    processing_time=time.time() - start_time,
                    whisper_model=self.model_name
                )

            # 检查结果是否为整数（可能是错误代码）
            if isinstance(result, int):
                logger.error(f"SenseVoice 返回整数错误代码: {result}")
                raise Exception(f"SenseVoice 返回错误代码: {result}")

            # 检查结果是否为字符串（可能是错误消息）
            if isinstance(result, str):
                logger.error(f"SenseVoice 返回字符串: {result}")
                if result.strip().isdigit() or result == "0":
                    raise Exception(f"SenseVoice 返回错误: {result}")
                # 如果是普通文本，直接作为转录结果
                return TranscriptionResult(
                    text=result,
                    language=language_str,
                    confidence=0.95,
                    segments=[TranscriptionSegment(
                        start_time=0.0,
                        end_time=0.0,
                        text=result,
                        confidence=0.95
                    )],
                    processing_time=time.time() - start_time,
                    whisper_model=self.model_name
                )

            # 检查结果是否为列表
            if not hasattr(result, '__len__') or len(result) == 0:
                logger.error(f"SenseVoice 返回空结果或非列表类型: {type(result)}")
                return TranscriptionResult(
                    text="",
                    language=language_str,
                    confidence=0.0,
                    segments=[],
                    processing_time=time.time() - start_time,
                    whisper_model=self.model_name
                )

            logger.info(f"结果长度: {len(result)}")

            # 处理第一个结果
            try:
                first_result = result[0]
            except (IndexError, TypeError, KeyError) as e:
                logger.error(f"无法访问 result[0]: {e}, result类型: {type(result)}")
                raise Exception(f"SenseVoice 结果格式异常，无法访问 result[0]: {str(e)}")

            logger.info(f"result[0] 类型: {type(first_result)}")
            logger.info(f"result[0] 内容: {repr(first_result)[:500]}")

            # 检查 first_result 是否为特殊类型
            if isinstance(first_result, (int, float)):
                error_code = int(first_result)
                logger.error(f"result[0] 是数字错误代码: {error_code}")
                raise Exception(f"SenseVoice 返回错误代码: {error_code}")

            if isinstance(first_result, str):
                logger.error(f"result[0] 是字符串: {first_result}")
                if first_result.strip().isdigit() or first_result == "0":
                    raise Exception(f"SenseVoice 返回错误: {first_result}")
                # 如果是普通文本，直接使用
                return TranscriptionResult(
                    text=first_result,
                    language=language_str,
                    confidence=0.95,
                    segments=[TranscriptionSegment(
                        start_time=0.0,
                        end_time=0.0,
                        text=first_result,
                        confidence=0.95
                    )],
                    processing_time=time.time() - start_time,
                    whisper_model=self.model_name
                )

            # 检查是否有长度属性
            if not hasattr(first_result, '__len__'):
                logger.error(f"result[0] 不支持长度检查: {type(first_result)}")
                # 尝试直接转换为字符串
                text_content = str(first_result)
                return TranscriptionResult(
                    text=text_content,
                    language=language_str,
                    confidence=0.95,
                    segments=[TranscriptionSegment(
                        start_time=0.0,
                        end_time=0.0,
                        text=text_content,
                        confidence=0.95
                    )],
                    processing_time=time.time() - start_time,
                    whisper_model=self.model_name
                )

            logger.info(f"result[0] 长度: {len(first_result)}")

            if len(first_result) == 0:
                logger.warning("SenseVoice 返回空结果")
                return TranscriptionResult(
                    text="",
                    language=language_str,
                    confidence=0.0,
                    segments=[],
                    processing_time=time.time() - start_time,
                    whisper_model=self.model_name
                )

            if progress_callback:
                progress_callback(80)

            # 提取转录文本和时间戳
            text = ""
            segments = []
            detected_lang = language_str if language_str != "auto" else "zh"

            logger.info(f"处理 SenseVoice 结果，共 {len(first_result)} 个片段")

            try:
                # SenseVoice 返回格式可能是多种格式，需要灵活处理
                # 格式1: 字符串列表 ["句子1", "句子2"]
                # 格式2: 字典列表 [{"sentence": "文本", "timestamp": [...]}]
                # 格式3: 单个字典 {"sentence": "文本", "timestamp": [...]}

                # 检查 first_result 的类型
                logger.info(f"first_result 类型: {type(first_result)}")

                # 如果 first_result 本身就是一个字典
                if isinstance(first_result, dict):
                    logger.info("检测到单个字典格式结果")
                    # 处理单个字典
                    sentence = first_result.get("sentence", "")
                    if not sentence:
                        # 尝试其他可能的键名
                        sentence = first_result.get("text", "")
                    if not sentence:
                        # 如果没有 sentence 键，直接将整个字典转换为字符串
                        sentence = str(first_result)

                    text += sentence

                    # 获取时间戳
                    start_time = 0.0
                    end_time = 0.0
                    timestamp = first_result.get("timestamp", [])
                    if len(timestamp) >= 2:
                        try:
                            start_time = float(timestamp[0]) / 1000.0
                            end_time = float(timestamp[1]) / 1000.0
                        except (ValueError, TypeError):
                            pass

                    # 获取语言
                    item_lang = first_result.get("language", detected_lang)
                    if item_lang:
                        detected_lang = item_lang

                    # 确保end_time大于start_time（验证要求）
                    if end_time <= start_time:
                        end_time = start_time + 0.001

                    segments.append(TranscriptionSegment(
                        start_time=start_time,
                        end_time=end_time,
                        text=sentence.strip(),
                        confidence=0.95
                    ))

                # 如果是列表或元组
                elif isinstance(first_result, (list, tuple)):
                    logger.info(f"检测到列表格式结果，长度: {len(first_result)}")
                    if len(first_result) == 0:
                        logger.warning("结果列表为空")
                    else:
                        # 检查列表中第一个元素的类型
                        first_element = first_result[0]
                        logger.info(f"列表首元素类型: {type(first_element)}")

                        # 如果是字符串列表
                        if isinstance(first_element, str):
                            logger.info("处理字符串列表")
                            for sentence in first_result:
                                try:
                                    clean_text = str(sentence).strip()
                                    if clean_text:
                                        text += clean_text
                                        segments.append(TranscriptionSegment(
                                            start_time=0.0,
                                            end_time=0.0,
                                            text=clean_text,
                                            confidence=0.95
                                        ))
                                except Exception as e:
                                    logger.warning(f"处理字符串片段失败: {e}")

                        # 如果是字典列表
                        elif isinstance(first_element, dict):
                            logger.info("处理字典列表")
                            for item in first_result:
                                try:
                                    # 获取句子文本
                                    sentence = item.get("sentence", "")
                                    if not sentence:
                                        sentence = item.get("text", "")
                                    if not sentence:
                                        sentence = str(item)

                                    text += sentence

                                    # 获取时间戳
                                    start_time = 0.0
                                    end_time = 0.0
                                    timestamp = item.get("timestamp", [])
                                    if len(timestamp) >= 2:
                                        try:
                                            start_time = float(timestamp[0]) / 1000.0
                                            end_time = float(timestamp[1]) / 1000.0
                                        except (ValueError, TypeError):
                                            pass

                                    # 获取语言
                                    item_lang = item.get("language", detected_lang)
                                    if item_lang:
                                        detected_lang = item_lang

                                    segments.append(TranscriptionSegment(
                                        start_time=start_time,
                                        end_time=end_time,
                                        text=sentence.strip(),
                                        confidence=0.95
                                    ))

                                except Exception as e:
                                    logger.warning(f"处理字典片段失败: {e}")
                                    import traceback
                                    logger.debug(traceback.format_exc())

                        else:
                            logger.warning(f"未知的列表元素类型: {type(first_element)}")
                            # 尝试将每个元素转换为字符串
                            for item in first_result:
                                try:
                                    item_text = str(item).strip()
                                    if item_text:
                                        text += item_text
                                        segments.append(TranscriptionSegment(
                                            start_time=0.0,
                                            end_time=0.0,
                                            text=item_text,
                                            confidence=0.95
                                        ))
                                except Exception as e:
                                    logger.warning(f"处理片段失败: {e}")
                else:
                    logger.warning(f"未知的 first_result 类型: {type(first_result)}")
                    # 尝试直接转换为字符串
                    text = str(first_result)
                    segments.append(TranscriptionSegment(
                        start_time=0.0,
                        end_time=0.0,
                        text=text,
                        confidence=0.95
                    ))

            except Exception as e:
                logger.error(f"处理 SenseVoice 结果时出错: {e}")
                import traceback
                logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")

            # 计算整体置信度
            try:
                if segments:
                    avg_confidence = sum(seg.confidence for seg in segments) / len(segments)
                    confidence = avg_confidence
                else:
                    confidence = 0.95  # 默认置信度
            except Exception as e:
                logger.warning(f"计算置信度时出错: {e}")
                confidence = 0.95

            processing_time = time.time() - start_time
            logger.info(f"转录完成，文本长度: {len(text)}, 片段数: {len(segments)}")

            # 文本后处理
            if text:
                # 步骤1: 清理特殊标记
                text = self._clean_special_tokens(text)
                # 更新segments中的文本
                for seg in segments:
                    seg.text = self._clean_special_tokens(seg.text)

                # 步骤2: 添加标点符号
                if self.enable_punctuation:
                    try:
                        logger.info("正在添加标点符号...")
                        text_with_punct = self._add_punctuation(text, detected_lang)
                        if text_with_punct and text_with_punct != text:
                            logger.info(f"标点符号添加成功")
                            text = text_with_punct
                            # 更新segments中的文本
                            for seg in segments:
                                if seg.text:
                                    seg.text = self._add_punctuation(seg.text, detected_lang)
                        else:
                            logger.info("标点符号处理无变化")
                    except Exception as e:
                        logger.warning(f"标点符号后处理失败: {e}，使用原始文本")

            # 最终验证：确保我们有有效的文本
            if not text or len(text.strip()) == 0:
                logger.warning("转录结果为空，返回空结果")
                return TranscriptionResult(
                    text="",
                    language=detected_lang,
                    confidence=0.0,
                    segments=[],
                    processing_time=processing_time,
                    whisper_model=self.model_name
                )

            return TranscriptionResult(
                text=text.strip(),
                language=detected_lang,
                confidence=confidence,
                segments=segments,
                processing_time=processing_time,
                whisper_model=self.model_name
            )

        except Exception as e:
            import traceback
            logger.error(f"SenseVoice 推理失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误详情: {str(e)}")
            logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
            raise Exception(f"SenseVoice 推理失败: {str(e)}")

    async def _transcribe_with_chunking(
        self,
        audio_path: str,
        language: str,
        with_timestamps: bool,
        progress_callback: Optional[Callable[[float], None]],
        start_time: float
    ) -> TranscriptionResult:
        """
        使用分块处理转录长音频

        Args:
            audio_path: 音频文件路径
            language: 语言代码
            with_timestamps: 是否包含时间戳
            progress_callback: 进度回调
            start_time: 开始时间

        Returns:
            TranscriptionResult: 转录结果
        """
        import time
        import os

        try:
            # 分割音频
            logger.info("开始分割音频...")
            chunks = await self.audio_chunker.split_audio(
                audio_path,
                temp_dir=self.model_cache_dir
            )

            if not chunks:
                raise Exception("音频分割失败，未生成任何块")

            logger.info(f"音频已分割为 {len(chunks)} 个块")

            # 处理每个块
            chunk_results = []
            total_chunks = len(chunks)

            for i, (chunk_path, chunk_start, chunk_end) in enumerate(chunks):
                try:
                    logger.info(f"处理块 {i+1}/{total_chunks}: {chunk_start:.1f}s - {chunk_end:.1f}s")

                    # 更新进度
                    if progress_callback:
                        progress = 20 + (60 * (i + 1) / total_chunks)
                        progress_callback(progress)

                    # 处理单个块
                    chunk_result = await self._transcribe_single_chunk(
                        chunk_path, language, with_timestamps, chunk_start, chunk_end
                    )
                    chunk_results.append(chunk_result)

                    # 释放 GPU 内存
                    if torch.cuda.is_available():
                        torch.cuda.empty_cache()

                except Exception as e:
                    logger.error(f"处理块 {i+1} 失败: {e}")
                    # 继续处理下一个块，不中断整个流程
                    chunk_results.append({
                        "text": "",
                        "segments": [],
                        "language": language,
                        "confidence": 0.0,
                        "processing_time": 0.0,
                        "start_time": chunk_start,
                        "end_time": chunk_end
                    })

            # 清理临时文件
            chunk_paths = [chunk[0] for chunk in chunks]
            await self.audio_chunker.cleanup_chunks(chunk_paths)

            # 合并结果
            logger.info("合并分块转录结果...")
            merged_result = self.audio_chunker.merge_results(
                chunk_results,
                overlap_seconds=self.chunk_overlap_seconds
            )

            # 后处理：清理特殊标记和添加标点符号
            final_text = merged_result.get("text", "")

            if final_text:
                # 清理特殊标记
                final_text = self._clean_special_tokens(final_text)

                # 添加标点符号（如果启用）
                if self.enable_punctuation:
                    try:
                        final_text = self._add_punctuation(final_text, language)
                    except Exception as e:
                        logger.warning(f"标点符号处理失败: {e}")

            # 构建最终的 TranscriptionResult
            processing_time = time.time() - start_time
            logger.info(f"分块转录完成，总耗时: {processing_time:.2f}秒")

            return TranscriptionResult(
                text=final_text.strip(),
                language=merged_result.get("language", language),
                confidence=merged_result.get("confidence", 0.95),
                segments=[],
                processing_time=processing_time,
                whisper_model=self.model_name
            )

        except Exception as e:
            import traceback
            logger.error(f"分块转录失败: {e}")
            logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
            raise Exception(f"分块转录失败: {str(e)}")

    async def _transcribe_single_chunk(
        self,
        chunk_path: str,
        language: str,
        with_timestamps: bool,
        chunk_start: float,
        chunk_end: float
    ) -> dict:
        """
        转录单个音频块

        Args:
            chunk_path: 音频块文件路径
            language: 语言代码
            with_timestamps: 是否包含时间戳
            chunk_start: 块开始时间
            chunk_end: 块结束时间

        Returns:
            dict: 转录结果
        """
        import time

        try:
            start = time.time()

            # 验证文件
            if not os.path.exists(chunk_path):
                raise Exception(f"音频块文件不存在: {chunk_path}")

            file_size = os.path.getsize(chunk_path)
            logger.debug(f"处理音频块: {chunk_path}, 大小: {file_size} 字节")

            # SenseVoice 推理参数
            rec_config_kwargs = {
                "batch_size_s": 300,
                "merge_vad": True,
                "merge_length_s": 5,
            }

            if language != "auto":
                rec_config_kwargs["language"] = language
            else:
                rec_config_kwargs["language"] = "auto"

            # 执行推理
            result = self.model.generate(
                input=chunk_path,
                cache_path=self.model_cache_dir,
                **rec_config_kwargs
            )

            processing_time = time.time() - start

            # 提取文本
            text = self._extract_text_from_result(result)

            return {
                "text": text,
                "segments": [],
                "language": language,
                "confidence": 0.95,
                "processing_time": processing_time,
                "start_time": chunk_start,
                "end_time": chunk_end
            }

        except Exception as e:
            logger.error(f"处理音频块失败: {e}")
            raise

    def _extract_text_from_result(self, result) -> str:
        """
        从 SenseVoice 结果中提取文本

        Args:
            result: SenseVoice 推理结果

        Returns:
            str: 提取的文本
        """
        text = ""

        try:
            # 检查结果是否为空
            if result is None:
                return ""

            # 检查结果是否为整数（可能是错误代码）
            if isinstance(result, int):
                logger.warning(f"SenseVoice 返回整数错误代码: {result}")
                return ""

            # 检查结果是否为字符串
            if isinstance(result, str):
                if result.strip().isdigit() or result == "0":
                    return ""
                return result

            # 检查结果是否为列表
            if not hasattr(result, '__len__') or len(result) == 0:
                return ""

            # 处理第一个结果
            try:
                first_result = result[0]
            except (IndexError, TypeError, KeyError):
                return ""

            # 检查 first_result 是否为特殊类型
            if isinstance(first_result, (int, float)):
                return ""

            if isinstance(first_result, str):
                if first_result.strip().isdigit() or first_result == "0":
                    return ""
                return first_result

            # 检查是否有长度属性
            if not hasattr(first_result, '__len__'):
                return str(first_result)

            if len(first_result) == 0:
                return ""

            # 提取文本
            if isinstance(first_result, dict):
                text = first_result.get("sentence", "")
                if not text:
                    text = first_result.get("text", "")
                if not text:
                    text = str(first_result)
            elif isinstance(first_result, (list, tuple)):
                for item in first_result:
                    if isinstance(item, str):
                        text += item
                    elif isinstance(item, dict):
                        sentence = item.get("sentence", "")
                        if not sentence:
                            sentence = item.get("text", "")
                        text += sentence
            else:
                text = str(first_result)

        except Exception as e:
            logger.warning(f"提取文本时出错: {e}")

        return text

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
    language: str = "auto",
    enable_punctuation: bool = True,
    clean_special_tokens: bool = True,
    enable_chunking: bool = True,
    chunk_duration_seconds: int = 180,
    chunk_overlap_seconds: int = 2,
    min_duration_for_chunking: int = 300
) -> SenseVoiceTranscriber:
    """
    创建 SenseVoice 转录器实例

    Args:
        model_name: 模型名称
        device: 计算设备 ('cpu', 'cuda', 'auto')
        model_cache_dir: 模型缓存目录
        language: 默认语言
        enable_punctuation: 是否添加标点符号
        clean_special_tokens: 是否清理特殊标记
        enable_chunking: 是否启用音频分块处理（推荐用于长音频）
        chunk_duration_seconds: 每块时长（秒），默认180秒（3分钟）
        chunk_overlap_seconds: 块之间重叠时间（秒），默认2秒
        min_duration_for_chunking: 超过此时长（秒）才启用分块，默认300秒（5分钟）

    Returns:
        SenseVoiceTranscriber: SenseVoice 转录器实例
    """
    return SenseVoiceTranscriber(
        model_name=model_name,
        device=device,
        model_cache_dir=model_cache_dir,
        language=language,
        enable_punctuation=enable_punctuation,
        clean_special_tokens=clean_special_tokens,
        enable_chunking=enable_chunking,
        chunk_duration_seconds=chunk_duration_seconds,
        chunk_overlap_seconds=chunk_overlap_seconds,
        min_duration_for_chunking=min_duration_for_chunking
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
