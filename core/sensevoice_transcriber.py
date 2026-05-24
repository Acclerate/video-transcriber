"""
SenseVoice 语音转录器
基于阿里巴巴达摩院的 SenseVoice 模型
支持多语言语音识别，对中文等亚洲语言效果更佳
"""

import os
import re
import time
import asyncio
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List, Callable, Tuple

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
    CharTimestamp,
    Language,
    OutputFormat,
    TimestampMode
)
from utils.subtitle_timing import fix_subtitle_segment_timing
from config.settings import settings

try:
    from utils.forced_aligner import (
        ForcedAligner,
        expand_char_timestamps_syllable_aware,
    )
    FA_AVAILABLE = True
except ImportError:
    FA_AVAILABLE = False
    ForcedAligner = None
    expand_char_timestamps_syllable_aware = None
    logger.warning("FA 强制对齐模块不可用")


class _SkipStandardParse(Exception):
    """内部控制流异常：跳过标准格式解析"""
    pass


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

    # 句子内标点（用于合并短 segments 时过滤）
    _SEGMENT_PUNCT_RE = re.compile(r'''[，。！？、；：""''（）()【】《》…—,.!?\s-]''')

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
        min_duration_for_chunking: int = 300,
        timestamp_mode: str = "none"
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
            timestamp_mode: 时间戳模式 ('none', 'sentence', 'char')
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
        self.timestamp_mode = timestamp_mode

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
            "yue": "yue",
            "ja": "ja",
            "ko": "ko",
        }

        # 音频停顿位置（用于优化字幕切分）
        self.silence_ranges: List[Tuple[float, float]] = []

        # FA 强制对齐器
        self._fa_aligner: Optional[Any] = None

    def _determine_device(self, device: Optional[str]) -> str:
        """确定计算设备"""
        if device == "auto" or device is None:
            if torch.cuda.is_available():
                device = "cuda"
                device_count = torch.cuda.device_count()
                device_name = torch.cuda.get_device_name(0) if device_count > 0 else "Unknown"
                logger.info(f"检测到CUDA ({device_count} 个设备: {device_name})，SenseVoice 使用GPU加速")
            else:
                device = "cpu"
                logger.warning("未检测到CUDA，SenseVoice 使用CPU（请安装带CUDA支持的PyTorch）")
        elif device == "cuda" and not torch.cuda.is_available():
            logger.warning("指定使用CUDA但未检测到，回退到CPU")
            logger.warning("如需使用GPU，请安装: pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu118")
            device = "cpu"
        elif device == "cuda":
            # 验证 CUDA 实际可用
            device_count = torch.cuda.device_count()
            device_name = torch.cuda.get_device_name(0) if device_count > 0 else "Unknown"
            logger.info(f"CUDA 设备信息: {device_count} 个设备, 主设备: {device_name}")

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

        # FunASR 的 device 参数在某些版本中不生效
        # 直接使用 device="cuda" 可能无法正确加载到 GPU
        # 解决方案: 先加载到 CPU，然后显式调用 .cuda() 移到 GPU
        logger.info(f"正在加载 SenseVoice 模型 (目标设备: {self.device})...")
        self.model = AutoModel(
            model=model_path,
            device="cpu",
            cache_dir=self.model_cache_dir,
            disable_pbar=False,
            disable_log=False,
        )

        # 如果需要使用 GPU，显式移到 GPU
        if self.device == "cuda" and torch.cuda.is_available():
            logger.info("正在将模型移至 GPU...")
            try:
                # FunASR AutoModel 有多个组件需要移到 GPU
                components_to_move = ['model', 'vad_model', 'punc_model', 'spk_model', 'frontend']
                moved_count = 0

                for comp_name in components_to_move:
                    if hasattr(self.model, comp_name):
                        comp = getattr(self.model, comp_name)
                        if comp is not None:
                            try:
                                if hasattr(comp, 'to'):
                                    comp.to("cuda")
                                    moved_count += 1
                                    logger.debug(f"  ✓ {comp_name} 已移至 GPU")
                            except Exception as e:
                                logger.debug(f"  ⚠ {comp_name} 移至 GPU 失败: {e}")

                # 如果没有组件被移动，尝试直接移动 AutoModel
                if moved_count == 0:
                    if hasattr(self.model, 'to'):
                        self.model.to("cuda")
                        logger.info("✓ AutoModel 已移至 GPU")
                    else:
                        logger.warning("⚠️ 无法将模型移至 GPU，使用 CPU 模式")
                else:
                    logger.info(f"✓ 共 {moved_count} 个组件已移至 GPU")
            except Exception as e:
                logger.warning(f"模型移至 GPU 失败: {e}，继续使用 CPU")

        load_time = time.time() - start_time
        logger.info(f"SenseVoice 模型加载完成 (耗时 {load_time:.2f} 秒)")

        # 检查 GPU 显存使用
        if self.device == "cuda" and torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated(0) / 1024**2
            cached = torch.cuda.memory_reserved(0) / 1024**2
            logger.info(f"GPU 显存使用: 已分配 {allocated:.2f} MB, 已缓存 {cached:.2f} MB")

            if allocated == 0:
                logger.warning("⚠️ GPU 显存占用为 0，模型可能在 CPU 上运行！")

        return self.model

    async def transcribe_audio(
        self,
        audio_path: str,
        language: Language = Language.AUTO,
        with_timestamps: bool = False,
        temperature: float = 0.0,
        progress_callback: Optional[Callable[[float], None]] = None,
        timestamp_mode: Optional[str] = None,
        silence_ranges: Optional[List[Tuple[float, float]]] = None,
        raw_audio_path: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        转录音频文件

        Args:
            audio_path: 音频文件路径
            language: 目标语言
            with_timestamps: 是否包含时间戳
            temperature: 采样温度 (SenseVoice 忽略此参数)
            progress_callback: 进度回调函数
            timestamp_mode: 时间戳模式 (覆盖初始化时的设置)
            silence_ranges: 音频停顿位置列表，用于优化字幕切分
            raw_audio_path: 原始音频路径，用于需要原始时间轴的后处理

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

            # 设置停顿位置（用于字幕切分优化）
            if silence_ranges:
                self.silence_ranges = silence_ranges
                logger.info(f"已设置 {len(silence_ranges)} 个停顿位置用于字幕切分")

            # 准备语言参数
            lang = self._map_language(language)

            # 确定实际的时间戳模式
            actual_timestamp_mode = timestamp_mode or self.timestamp_mode

            # 执行转录
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None,
                self._transcribe_sync,
                audio_path,
                lang,
                with_timestamps,
                progress_callback,
                actual_timestamp_mode,
                raw_audio_path
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
            Language.CHINESE: "zh",
            Language.ENGLISH: "en",
            Language.JAPANESE: "ja",
            Language.KOREAN: "ko",
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
            if not cleaned_text:
                logger.warning(f"清理后文本为空，原始内容: {text[:200]}")

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
                # 先加载到 CPU
                model = AutoModel(
                    model=model_path,
                    device="cpu",
                    cache_dir=self.model_cache_dir,
                    disable_pbar=False,
                    disable_log=False,
                )

                # 如果需要使用 GPU，显式移到 GPU
                if self.device == "cuda" and torch.cuda.is_available():
                    try:
                        # 移动所有组件到 GPU
                        components_to_move = ['model', 'vad_model', 'punc_model', 'spk_model', 'frontend']
                        moved_count = 0

                        for comp_name in components_to_move:
                            if hasattr(model, comp_name):
                                comp = getattr(model, comp_name)
                                if comp is not None and hasattr(comp, 'to'):
                                    try:
                                        comp.to("cuda")
                                        moved_count += 1
                                    except:
                                        pass

                        if moved_count > 0:
                            logger.info(f"✓ 标点符号模型已移至 GPU ({moved_count} 个组件)")
                    except Exception as e:
                        logger.warning(f"标点符号模型移至 GPU 失败: {e}，继续使用 CPU")

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
                device=self.device,  # 确保使用正确的设备
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
        progress_callback: Optional[Callable[[float], None]] = None,
        timestamp_mode: str = "none",
        raw_audio_path: Optional[str] = None,
    ) -> TranscriptionResult:
        """同步执行转录"""
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

            # 确定实际的时间戳模式
            actual_mode = timestamp_mode or self.timestamp_mode

            logger.info(f"开始 SenseVoice 转录: {audio_path}")
            logger.info(f"语言模式: {language_str}, 时间戳模式: {actual_mode}")

            # ========== 音频分块处理 ==========
            # 检查是否需要对音频进行分块处理
            should_chunk = False
            if self.enable_chunking and self.audio_chunker:
                should_chunk = self.audio_chunker.should_chunk(audio_path)
                audio_duration = self.audio_chunker.get_audio_duration(audio_path)

                if should_chunk:
                    logger.info(f"音频时长 {audio_duration:.1f}s 超过阈值 {self.min_duration_for_chunking}s，"
                               f"将启用分块处理（每块 {self.chunk_duration_seconds}s）")
                    # 使用同步分块处理方法
                    return self._transcribe_with_chunking_sync(
                        audio_path, language_str, with_timestamps, progress_callback, start_time,
                        timestamp_mode=actual_mode,
                        raw_audio_path=raw_audio_path
                    )
                else:
                    logger.info(f"音频时长 {audio_duration:.1f}s 不需要分块处理")
            # ========== 音频分块处理结束 ==========

            # SenseVoice 推理参数
            rec_config_kwargs = self._build_rec_config(language_str, actual_mode)

            # 执行推理
            logger.info("正在执行 SenseVoice 推理...")
            logger.info(f"推理参数: batch_size_s=60, merge_vad=True, merge_length_s=5, language={language_str}")
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
            char_timestamps = []
            detected_lang = language_str if language_str != "auto" else "zh"

            logger.info(f"处理 SenseVoice 结果，共 {len(first_result)} 个片段")

            # 检查是否为逐字时间戳格式 (output_timestamp=True 的输出)
            # 格式: first_result 中每个条目包含 "words" 和 "timestamp" 键
            is_char_timestamp_format = False
            if isinstance(first_result, (list, tuple)) and len(first_result) > 0:
                first_item = first_result[0]
                if isinstance(first_item, dict) and "words" in first_item:
                    is_char_timestamp_format = True
            elif isinstance(first_result, dict) and "words" in first_result:
                is_char_timestamp_format = True

            if is_char_timestamp_format and actual_mode in ("char", "sentence"):
                logger.info("检测到逐字时间戳格式结果 (output_timestamp=True)")
                try:
                    # 将 first_result 统一为列表
                    result_entries = first_result if isinstance(first_result, (list, tuple)) else [first_result]
                    all_char_ts = []

                    for entry_idx, entry in enumerate(result_entries):
                        if not isinstance(entry, dict):
                            continue

                        entry_text = entry.get("text", "")
                        entry_text = self._clean_special_tokens(entry_text)

                        words = entry.get("words", [])
                        timestamps = entry.get("timestamp", [])

                        if not words or not timestamps:
                            logger.warning(f"条目 {entry_idx} 的 words 或 timestamp 为空，跳过")
                            if entry_text:
                                text += entry_text
                            continue

                        # 处理长度不匹配
                        if len(words) != len(timestamps):
                            logger.warning(
                                f"条目 {entry_idx}: words({len(words)}) 与 timestamp({len(timestamps)}) "
                                f"长度不匹配，截断到较短长度"
                            )
                            min_len = min(len(words), len(timestamps))
                            words = words[:min_len]
                            timestamps = timestamps[:min_len]

                        # 提取逐字时间戳，跳过特殊标记
                        entry_char_ts = []
                        entry_chars = []
                        for w, ts in zip(words, timestamps):
                            if not isinstance(ts, (list, tuple)) or len(ts) < 2:
                                continue
                            # 跳过特殊标记
                            clean_w = self._clean_special_tokens(str(w))
                            if not clean_w or clean_w.startswith("<|") or clean_w.startswith("|>"):
                                continue
                            try:
                                start_s = float(ts[0]) / 1000.0
                                end_s = float(ts[1]) / 1000.0
                                if end_s < start_s:
                                    continue
                                entry_char_ts.append(CharTimestamp(
                                    word=clean_w, start=round(start_s, 3), end=round(end_s, 3)
                                ))
                                entry_chars.append(clean_w)
                            except (ValueError, TypeError) as e:
                                logger.debug(f"跳过无效时间戳: word={w}, ts={ts}, err={e}")
                                continue

                        all_char_ts.extend(entry_char_ts)
                        entry_full_text = "".join(entry_chars) if entry_chars else entry_text
                        if entry_full_text:
                            text += entry_full_text
                            # 为每个 VAD 段创建一个 segment
                            if entry_char_ts:
                                segments.append(TranscriptionSegment(
                                    start_time=entry_char_ts[0].start,
                                    end_time=entry_char_ts[-1].end,
                                    text=entry_full_text,
                                    confidence=0.95,
                                    char_timestamps=entry_char_ts
                                ))
                            else:
                                segments.append(TranscriptionSegment(
                                    start_time=0.0, end_time=0.0,
                                    text=entry_full_text, confidence=0.95
                                ))

                    char_timestamps = all_char_ts
                    logger.info(f"时间戳提取完成: 共 {len(segments)} 个片段, {len(all_char_ts)} 个字/词")

                except Exception as e:
                    logger.error(f"处理逐字时间戳结果时出错: {e}")
                    import traceback
                    logger.error(traceback.format_exc())
                    # 回退到标准解析
                    is_char_timestamp_format = False
                    text = ""
                    segments = []
                    char_timestamps = []

            # 标准格式解析（当逐字时间戳未处理时执行）
            try:
                # 如果逐字时间戳已成功提取，跳过标准解析
                if text:
                    raise _SkipStandardParse()

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

                                    # 确保 end_time >= start_time
                                    if end_time < start_time:
                                        end_time = start_time + 0.001

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

            except _SkipStandardParse:
                logger.info("逐字时间戳已处理，跳过标准解析")
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

            # 保存 VAD 分段信息（SenseVoice 的 merge_vad 分段，包含准确的人声起止时间）
            vad_segments = list(segments) if segments else []

            # 文本后处理
            if text:
                # 步骤1: 清理特殊标记
                raw_text = self._clean_special_tokens(text)

                # 步骤2: FA 强制对齐（使用原始文本获取精确时间戳）
                if progress_callback:
                    progress_callback(85)

                fa_char_ts: List[CharTimestamp] = []
                use_fa = FA_AVAILABLE and actual_mode in ("char", "sentence")

                if use_fa and raw_text:
                    try:
                        logger.info("尝试使用 FA 强制对齐获取精确时间戳...")
                        fa_audio_path = raw_audio_path or audio_path
                        fa_text, fa_char_ts = self._align_with_fa(fa_audio_path, raw_text)
                        if fa_text and fa_char_ts and len(fa_text) == len(fa_char_ts):
                            raw_text = fa_text
                            logger.info(f"使用 FA 文本，长度={len(raw_text)}")
                    finally:
                        if self._fa_aligner is not None:
                            self._fa_aligner.unload_model()
                            self._fa_aligner = None

                # 选择最佳时间戳来源
                if fa_char_ts:
                    logger.info(f"FA 对齐成功: {len(fa_char_ts)} 个时间戳")
                    char_timestamps = fa_char_ts
                else:
                    logger.debug("使用 SenseVoice 原始时间戳")

                # 步骤3: 添加标点符号（仅用于确定自然断句位置）
                if progress_callback:
                    progress_callback(90)

                punctuated_text = raw_text
                if self.enable_punctuation:
                    try:
                        logger.info("正在添加标点符号...")
                        text_with_punct = self._add_punctuation(raw_text, detected_lang)
                        if text_with_punct and text_with_punct != raw_text:
                            logger.info(f"标点符号添加成功")
                            punctuated_text = text_with_punct
                        else:
                            logger.info("标点符号处理无变化")
                    except Exception as e:
                        logger.warning(f"标点符号后处理失败: {e}，使用原始文本")

                # 步骤4: 基于标点断句 + 时间戳对齐
                # 字幕文本不含标点，标点仅用于确定断句位置
                if progress_callback:
                    progress_callback(95)

                if actual_mode in ("char", "sentence") and char_timestamps:
                    if vad_segments:
                        segments = self._build_segments_vad_first(
                            vad_segments, char_timestamps, punctuated_text, raw_text,
                            silence_ranges=getattr(self, 'silence_ranges', None),
                        )
                    else:
                        segments = self._build_segments_by_punctuation_then_align(
                            raw_text, punctuated_text, char_timestamps
                        )

                    # VAD 边界锚定
                    if vad_segments and segments:
                        try:
                            from utils.subtitle_timing import anchor_segments_to_vad
                            segments = anchor_segments_to_vad(segments, vad_segments)
                        except Exception as e:
                            logger.warning(f"VAD 边界锚定失败: {e}")

                    # 静音区间约束
                    silence = getattr(self, 'silence_ranges', None)
                    if silence and segments:
                        try:
                            from utils.subtitle_timing import enforce_silence_boundaries
                            segments = enforce_silence_boundaries(segments, silence)
                        except Exception as e:
                            logger.warning(f"静音边界约束失败: {e}")

                # 文本模式使用带标点的文本，字幕模式使用原始文本（不含标点）
                text = punctuated_text if actual_mode == "none" else raw_text

            # 最终验证：确保我们有有效的文本
            if not text or not text.strip():
                logger.warning(f"转录结果为空！音频文件: {audio_path}")
                logger.warning(f"segments 数量: {len(segments)}")
                if segments:
                    logger.warning(f"前3个 segments: {[s.text[:50] for s in segments[:3]]}")
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
                whisper_model=self.model_name,
                char_timestamps=char_timestamps
            )

        except Exception as e:
            import traceback
            logger.error(f"SenseVoice 推理失败: {e}")
            logger.error(f"错误类型: {type(e).__name__}")
            logger.error(f"错误详情: {str(e)}")
            logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
            raise Exception(f"SenseVoice 推理失败: {str(e)}")

    def _transcribe_with_chunking_sync(
        self,
        audio_path: str,
        language: str,
        with_timestamps: bool,
        progress_callback: Optional[Callable[[float], None]],
        start_time: float,
        timestamp_mode: str = "none",
        raw_audio_path: Optional[str] = None,
    ) -> TranscriptionResult:
        """
        使用分块处理转录长音频（同步版本）

        Args:
            audio_path: 音频文件路径
            language: 语言代码
            with_timestamps: 是否包含时间戳
            progress_callback: 进度回调
            start_time: 开始时间
            timestamp_mode: 时间戳模式
            raw_audio_path: 原始音频路径（用于 FA 对齐）

        Returns:
            TranscriptionResult: 转录结果
        """

        try:
            # 分割音频 - 同步调用
            logger.info("开始分割音频...")
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                chunks = loop.run_until_complete(self.audio_chunker.split_audio(
                    audio_path,
                    temp_dir=self.model_cache_dir
                ))
            finally:
                loop.close()

            if not chunks:
                raise Exception("音频分割失败，未生成任何块")

            logger.info(f"音频已分割为 {len(chunks)} 个块")

            # 预加载 FA 模型（整个 chunking session 复用，避免逐块加载/卸载）
            if FA_AVAILABLE and timestamp_mode in ("char", "sentence"):
                try:
                    from utils.forced_aligner import ForcedAligner
                    self._fa_aligner = ForcedAligner(
                        model_cache_dir=self.model_cache_dir,
                        device=self.device,
                        force_time_shift=settings.FA_TIME_OFFSET,
                    )
                    if not self._fa_aligner.load_model():
                        self._fa_aligner = None
                except Exception as e:
                    logger.warning(f"FA 模型预加载失败，将使用 SenseVoice 时间戳: {e}")
                    self._fa_aligner = None

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

                    # 处理单个块 - 同步调用
                    chunk_result = self._transcribe_single_chunk_sync(
                        chunk_path, language, with_timestamps, chunk_start, chunk_end,
                        timestamp_mode=timestamp_mode
                    )
                    chunk_results.append(chunk_result)

                    # 记录每个块的文本长度
                    chunk_text = chunk_result.get("text", "")
                    logger.info(f"块 {i+1} 转录完成: 文本长度 {len(chunk_text)} 字符")

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

            # 清理临时文件 - 同步调用
            chunk_paths = [chunk[0] for chunk in chunks]
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.audio_chunker.cleanup_chunks(chunk_paths))
            finally:
                loop.close()

            # 卸载 FA 模型（整个 session 结束后统一释放）
            if self._fa_aligner is not None:
                self._fa_aligner.unload_model()
                self._fa_aligner = None

            # 合并结果
            logger.info("合并分块转录结果...")
            merged_result = self.audio_chunker.merge_results(
                chunk_results,
                overlap_seconds=self.chunk_overlap_seconds
            )

            return self._postprocess_chunked_result(
                merged_result, language, timestamp_mode, start_time,
                silence_ranges=getattr(self, 'silence_ranges', None),
            )

        except Exception as e:
            # 确保 FA 模型在异常时也被释放
            if getattr(self, '_fa_aligner', None) is not None:
                self._fa_aligner.unload_model()
                self._fa_aligner = None
            import traceback
            logger.error(f"分块转录失败: {e}")
            logger.error(f"堆栈跟踪:\n{traceback.format_exc()}")
            raise Exception(f"分块转录失败: {str(e)}")

    def _transcribe_single_chunk_sync(
        self,
        chunk_path: str,
        language: str,
        with_timestamps: bool,
        chunk_start: float,
        chunk_end: float,
        timestamp_mode: str = "none",
        raw_audio_path: Optional[str] = None,
    ) -> dict:
        """
        转录单个音频块（同步版本）

        Args:
            chunk_path: 音频块文件路径
            language: 语言代码
            with_timestamps: 是否包含时间戳
            chunk_start: 块开始时间
            chunk_end: 块结束时间
            timestamp_mode: 时间戳模式
            raw_audio_path: 原始音频路径（用于 FA 对齐）

        Returns:
            dict: 转录结果
        """

        try:
            start = time.time()

            # 验证文件
            if not os.path.exists(chunk_path):
                raise Exception(f"音频块文件不存在: {chunk_path}")

            file_size = os.path.getsize(chunk_path)
            logger.debug(f"处理音频块: {chunk_path}, 大小: {file_size} 字节")

            # SenseVoice 推理参数
            rec_config_kwargs = self._build_rec_config(language, timestamp_mode)

            # 执行推理
            result = self.model.generate(
                input=chunk_path,
                cache_path=self.model_cache_dir,
                **rec_config_kwargs
            )

            processing_time = time.time() - start

            # 提取文本
            text = self._extract_text_from_result(result)

            # 提取 VAD 分段（SenseVoice merge_vad 产生的人声分段）
            chunk_vad_segments = self._extract_vad_segments_from_result(result, chunk_start)

            # 提取或生成逐字时间戳
            char_ts_list = []
            use_fa = FA_AVAILABLE and timestamp_mode in ("char", "sentence")

            if timestamp_mode in ("char", "sentence"):
                # 首先尝试从 SenseVoice 结果提取时间戳
                char_ts_list = self._extract_char_ts_from_raw_result(result, chunk_start)
                sv_ts_count = len(char_ts_list)

                # 优先使用预加载的 FA 模型，回退到逐块加载
                fa_aligner = getattr(self, '_fa_aligner', None)
                if use_fa and text and fa_aligner is not None:
                    try:
                        logger.info(f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: 使用预加载 FA 强制对齐...")
                        fa_text, fa_char_ts = fa_aligner.align(chunk_path, text, time_offset=chunk_start)
                        if fa_char_ts:
                            fa_ts_count = len(fa_char_ts)
                            text_len = len(text)
                            logger.info(f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: FA 对齐成功，{fa_ts_count} 个精确时间戳 (文本 {text_len} 字符)")
                            if fa_text and len(fa_text) == text_len and fa_ts_count == text_len:
                                text = fa_text
                                char_ts_list = [
                                    {"word": ts.word, "start": ts.start, "end": ts.end}
                                    for ts in fa_char_ts
                                ]
                            else:
                                logger.warning(
                                    f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: FA 文本({len(fa_text or '')})"
                                    f"/时间戳({fa_ts_count})与原文({text_len})不匹配，使用 SenseVoice 时间戳({sv_ts_count})"
                                )
                        else:
                            logger.info(f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: FA 未产生时间戳，使用 SenseVoice")
                    except Exception as e:
                        logger.warning(f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: FA 对齐失败: {e}")
                elif use_fa and text:
                    # 无预加载 FA，回退到逐块加载方式
                    try:
                        logger.info(f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: 尝试 FA 强制对齐...")
                        fa_text, fa_char_ts = self._align_with_fa(chunk_path, text, time_offset=chunk_start)
                        if fa_char_ts:
                            fa_ts_count = len(fa_char_ts)
                            text_len = len(text)
                            logger.info(f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: FA 对齐成功，{fa_ts_count} 个精确时间戳 (文本 {text_len} 字符)")
                            if fa_text and len(fa_text) == text_len and fa_ts_count == text_len:
                                text = fa_text
                                logger.info(f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: 使用 FA 文本，长度={len(text)}")
                                char_ts_list = [
                                    {"word": ts.word, "start": ts.start, "end": ts.end}
                                    for ts in fa_char_ts
                                ]
                            else:
                                logger.warning(
                                    f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: FA 文本({len(fa_text or '')})"
                                    f"/时间戳({fa_ts_count})与原文({text_len})不匹配，使用 SenseVoice 时间戳({sv_ts_count})"
                                )
                        else:
                            logger.info(f"块 {chunk_start:.1f}s-{chunk_end:.1f}s: FA 未产生时间戳，使用 SenseVoice")
                    finally:
                        if self._fa_aligner is not None:
                            self._fa_aligner.unload_model()
                            self._fa_aligner = None

            return {
                "text": text,
                "segments": [],
                "vad_segments": chunk_vad_segments,
                "language": language,
                "confidence": 0.95,
                "processing_time": processing_time,
                "start_time": chunk_start,
                "end_time": chunk_end,
                "char_timestamps": char_ts_list
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

    def _build_rec_config(self, language: str, timestamp_mode: str = "none") -> dict:
        """构建 SenseVoice 推理参数（消除多处重复）"""
        kwargs = {
            "batch_size_s": 60,
            "merge_vad": True,
            "merge_length_s": 5,
            "device": self.device,
        }
        kwargs["language"] = language

        if timestamp_mode in ("char", "sentence"):
            kwargs["output_timestamp"] = True
            if FA_AVAILABLE:
                logger.info(f"已启用 SenseVoice output_timestamp fallback: {timestamp_mode}，FA 成功后将覆盖为精确时间戳")
            else:
                logger.info(f"已启用 SenseVoice output_timestamp: {timestamp_mode}")
        return kwargs

    def _align_with_fa(
        self, audio_path: str, text: str, time_offset: float = 0.0
    ) -> Tuple[Optional[str], List[CharTimestamp]]:
        """使用 FA 强制对齐模型获取精确的逐字时间戳"""
        try:
            if self._fa_aligner is None:
                if not FA_AVAILABLE:
                    return None, []
                self._fa_aligner = ForcedAligner(
                    model_cache_dir=self.model_cache_dir,
                    device=self.device,
                    force_time_shift=settings.FA_TIME_OFFSET,
                )

            if not self._fa_aligner._loaded:
                loaded = self._fa_aligner.load_model()
                if not loaded:
                    logger.warning("FA 模型加载失败，回退到 SenseVoice 时间戳")
                    return None, []

            return self._fa_aligner.align(audio_path, text, time_offset=time_offset)

        except Exception as e:
            logger.warning(f"FA 强制对齐异常: {e}，回退到 SenseVoice 时间戳")
            return None, []

    def _build_segments_vad_first(
        self,
        vad_segments: List[TranscriptionSegment],
        char_timestamps: List[CharTimestamp],
        punctuated_text: str,
        raw_text: str,
        max_chars: int = 25,
        silence_ranges: List[Tuple[float, float]] = None,
    ) -> List[TranscriptionSegment]:
        """
        VAD 分段优先的字幕构建策略。

        保留 SenseVoice VAD 检测到的人声起止边界作为字幕时间，
        仅当 VAD 分段文本过长时在标点处切分。纯中文优化。

        Args:
            vad_segments: SenseVoice VAD 分段（含准确的 start_time/end_time）
            char_timestamps: FA 或 SenseVoice 的逐字时间戳
            punctuated_text: 带标点文本（仅用于确定切分位置）
            raw_text: 原始文本（不含标点）
            max_chars: 单条字幕最大字符数，超过则切分
        """
        if not vad_segments:
            return []

        # 构建全文字符→时间映射
        char_time_map = self._build_raw_char_time_map(char_timestamps, raw_text)

        # 用静音位置校正时间戳漂移
        if silence_ranges and char_time_map:
            char_time_map = self._calibrate_char_time_map(char_time_map, silence_ranges)

        # 为每个 VAD 分段在 punctuated_text 中定位对应的标点位置
        # 通过 VAD 分段文本在 raw_text 中的位置来定位
        raw_pos = 0
        punct_to_raw = self._build_punct_to_raw_map(punctuated_text, raw_text)

        result_segments: List[TranscriptionSegment] = []

        for vad_seg in vad_segments:
            seg_text = vad_seg.text.strip()
            if not seg_text:
                continue

            # 在 raw_text 中找到该 VAD 分段文本的位置
            seg_start_in_raw = raw_text.find(seg_text, raw_pos)
            if seg_start_in_raw < 0:
                seg_start_in_raw = raw_pos
            seg_end_in_raw = seg_start_in_raw + len(seg_text)
            raw_pos = seg_end_in_raw

            # 短句：直接使用 VAD 分段的时间边界
            if len(seg_text) <= max_chars:
                result_segments.append(TranscriptionSegment(
                    start_time=vad_seg.start_time,
                    end_time=vad_seg.end_time,
                    text=seg_text,
                    confidence=vad_seg.confidence,
                    char_timestamps=getattr(vad_seg, "char_timestamps", []),
                ))
                continue

            # 长句：在标点处切分
            sub_segments = self._split_vad_segment_at_punctuation(
                seg_text, seg_start_in_raw, seg_end_in_raw,
                vad_seg.start_time, vad_seg.end_time,
                punctuated_text, punct_to_raw, char_time_map,
                max_chars, raw_text,
            )
            result_segments.extend(sub_segments)

        # 回退补全：VAD 段文本未覆盖 raw_text 尾部时，用 char_time_map 补全
        if raw_pos < len(raw_text) and char_time_map:
            uncovered_text = raw_text[raw_pos:].strip()
            if uncovered_text:
                uncovered_start = raw_pos
                uncovered_end = len(raw_text)
                logger.info(
                    f"VAD 段未覆盖 raw_text 尾部: 位置 {raw_pos}/{len(raw_text)}, "
                    f"未覆盖 {len(uncovered_text)} 字符, 使用 char_time_map 补全"
                )
                t_start = char_time_map[uncovered_start][0] if uncovered_start < len(char_time_map) else (result_segments[-1].end_time if result_segments else 0.0)
                t_end = char_time_map[min(uncovered_end - 1, len(char_time_map) - 1)][1] if char_time_map else t_start
                if t_end <= t_start:
                    avg_dur = (char_time_map[-1][1] - char_time_map[0][0]) / len(char_time_map) if char_time_map else 0.1
                    t_end = t_start + len(uncovered_text) * max(0.05, min(0.3, avg_dur))
                tail_segments = self._split_vad_segment_at_punctuation(
                    uncovered_text, uncovered_start, uncovered_end,
                    t_start, t_end,
                    punctuated_text, punct_to_raw, char_time_map,
                    max_chars, raw_text,
                )
                if tail_segments:
                    result_segments.extend(tail_segments)
                    logger.info(f"尾部补全: 追加 {len(tail_segments)} 条字幕")
                else:
                    logger.warning(f"尾部补全失败: 未能为 {len(uncovered_text)} 字符生成字幕")

        logger.info(f"VAD-first 分段: {len(vad_segments)} 个 VAD 段 → {len(result_segments)} 条字幕")
        return self._dedupe_and_fix_segment_timing(result_segments, subtitle_hold_seconds=0.0)

    def _build_raw_char_time_map(
        self,
        char_timestamps: List[CharTimestamp],
        raw_text: str,
    ) -> List[Tuple[float, float]]:
        """构建 raw_text 每个字符的时间映射 [(start, end), ...]

        使用内容对齐而非顺序映射，正确处理分块合并后 text 与 char_ts
        因重叠区域不同处理策略导致的位置偏移问题。
        """
        expanded_ts = self._expand_subtitle_char_timestamps([
            ts for ts in char_timestamps if ts.word and ts.end >= ts.start
        ])
        if not expanded_ts:
            return []

        # 展开为逐字符时间戳
        char_times: List[Tuple[float, float]] = []
        ts_text_parts: List[str] = []
        for ts in expanded_ts:
            n_chars = len(ts.word)
            if n_chars == 1:
                char_times.append((ts.start, ts.end))
            else:
                dur = (ts.end - ts.start) / n_chars
                for i in range(n_chars):
                    char_times.append((
                        round(ts.start + dur * i, 3),
                        round(ts.start + dur * (i + 1), 3),
                    ))
            ts_text_parts.append(ts.word)

        if not char_times:
            return []

        ts_text = "".join(ts_text_parts)

        # --- 内容对齐：ts_text 是 raw_text 的子序列 ---
        # raw_text 包含重叠区域的重复文本，ts_text 已去除重叠 char_ts
        # 用双指针对齐，将 char_times 映射到 raw_text 的正确位置
        char_time_map: List[Optional[Tuple[float, float]]] = [None] * len(raw_text)

        ts_idx = 0
        for raw_idx in range(len(raw_text)):
            if ts_idx < len(ts_text) and raw_text[raw_idx] == ts_text[ts_idx]:
                char_time_map[raw_idx] = char_times[ts_idx]
                ts_idx += 1

        matched = sum(1 for x in char_time_map if x is not None)
        if matched < len(char_times) * 0.5:
            logger.warning(
                f"内容对齐匹配率低: {matched}/{len(char_times)} "
                f"({matched / len(char_times) * 100:.1f}%)，回退到顺序映射"
            )
            # 回退到顺序映射
            result = list(char_times)
            while len(result) < len(raw_text):
                if result:
                    last = result[-1]
                    avg_dur = max(0.05, min(0.25, last[1] - last[0]))
                    result.append((round(last[1], 3), round(last[1] + avg_dur, 3)))
                else:
                    result.append((0.0, 0.1))
            return result[:len(raw_text)]

        # 填充未映射的位置（重叠文本和 deficit 区域）
        self._fill_char_time_map_gaps(char_time_map, char_times)

        logger.info(
            f"char_time_map 内容对齐: {matched}/{len(raw_text)} 个字符有精确时间戳, "
            f"{len(raw_text) - matched} 个字符使用插值"
        )
        return char_time_map

    def _fill_char_time_map_gaps(
        self,
        char_time_map: List[Optional[Tuple[float, float]]],
        char_times: List[Tuple[float, float]],
    ) -> None:
        """填充 char_time_map 中 None 的位置（插值/外推）"""
        n = len(char_time_map)

        # 收集所有已映射的位置
        mapped: List[Tuple[int, Tuple[float, float]]] = [
            (i, char_time_map[i]) for i in range(n) if char_time_map[i] is not None
        ]

        if not mapped:
            avg_dur = 0.1
            for i in range(n):
                char_time_map[i] = (round(i * avg_dur, 3), round((i + 1) * avg_dur, 3))
            return

        # 前缀：第一个映射位置之前的部分，向前外推
        first_idx, (first_start, first_end) = mapped[0]
        if first_idx > 0:
            avg_dur = max(0.05, min(0.3, first_end - first_start))
            for i in range(first_idx):
                t_start = first_start - avg_dur * (first_idx - i)
                t_end = first_start - avg_dur * (first_idx - i - 1)
                char_time_map[i] = (round(t_start, 3), round(t_end, 3))

        # 中间间隙：在相邻映射位置之间线性插值
        for k in range(len(mapped) - 1):
            idx_a, (start_a, end_a) = mapped[k]
            idx_b, (start_b, end_b) = mapped[k + 1]
            gap_len = idx_b - idx_a - 1
            if gap_len > 0:
                total_dur = start_b - end_a
                char_dur = total_dur / (gap_len + 1)
                char_dur = max(0.02, char_dur)
                for j in range(gap_len):
                    pos = idx_a + 1 + j
                    t_start = round(end_a + char_dur * j, 3)
                    t_end = round(t_start + char_dur, 3)
                    char_time_map[pos] = (t_start, t_end)

        # 后缀：最后一个映射位置之后的部分，向后外推
        last_idx, (last_start, last_end) = mapped[-1]
        if last_idx < n - 1:
            tail_n = min(200, len(mapped))
            if tail_n >= 2:
                tail_start_idx, (tail_start_time, _) = mapped[-tail_n]
                tail_dur = last_end - tail_start_time
                tail_chars = last_idx - tail_start_idx
                avg_dur = tail_dur / tail_chars if tail_chars > 0 else 0.1
            else:
                avg_dur = max(0.05, last_end - last_start)
            avg_dur = max(0.05, min(0.25, avg_dur))
            for i in range(last_idx + 1, n):
                prev_end = char_time_map[i - 1][1]
                char_time_map[i] = (round(prev_end, 3), round(prev_end + avg_dur, 3))

    def _calibrate_char_time_map(
        self,
        char_time_map: List[Tuple[float, float]],
        silence_ranges: List[Tuple[float, float]],
    ) -> List[Tuple[float, float]]:
        """用静音位置作为锚点校正 char_time_map 的渐进漂移。

        算法：
        1. 对每个显著静音区间，找到 char_time_map 中该静音之后的第一个条目
        2. 该条目的 start_time 应该接近静音结束时间 sil_end
        3. 计算 drift = actual_start - sil_end
        4. 用分段线性插值在锚点之间修正所有时间戳
        """
        if not char_time_map or not silence_ranges or len(char_time_map) < 10:
            return char_time_map

        # 只使用较长的静音 (>0.25s) 作为锚点
        sig_silences = [(s, e) for s, e in silence_ranges if (e - s) > 0.25]
        if len(sig_silences) < 3:
            return char_time_map

        # 为每个静音找到 char_time_map 中紧随其后的条目
        anchors = [(0, 0.0)]  # (char_idx, drift)
        for sil_start, sil_end in sig_silences:
            # 线性搜索第一个 start_time >= sil_end 的条目
            for ci in range(len(char_time_map)):
                if char_time_map[ci][0] >= sil_end - 0.05:
                    drift = char_time_map[ci][0] - sil_end
                    if abs(drift) < 3.0:  # 忽略异常大的漂移
                        anchors.append((ci, drift))
                    break

        if len(anchors) < 3:
            return char_time_map

        # 去重：相同 char_idx 只保留第一个
        seen = set()
        deduped = []
        for a in anchors:
            if a[0] not in seen:
                seen.add(a[0])
                deduped.append(a)
        anchors = deduped
        anchors.sort(key=lambda x: x[0])

        logger.info(
            f"char_time_map 静音校准: {len(anchors)} 个锚点, "
            f"漂移范围 [{min(d for _, d in anchors):.3f}s, {max(d for _, d in anchors):.3f}s]"
        )

        # 分段线性修正
        corrected = list(char_time_map)
        for seg_idx in range(len(anchors) - 1):
            start_ci, start_drift = anchors[seg_idx]
            end_ci, end_drift = anchors[seg_idx + 1]
            span = end_ci - start_ci
            if span <= 0:
                continue
            for ci in range(start_ci, min(end_ci + 1, len(corrected))):
                t = (ci - start_ci) / span
                correction = start_drift + t * (end_drift - start_drift)
                s, e = corrected[ci]
                corrected[ci] = (round(s - correction, 3), round(e - correction, 3))

        # 最后一个锚点之后，用最终漂移值修正
        if anchors:
            last_ci, last_drift = anchors[-1]
            for ci in range(last_ci + 1, len(corrected)):
                s, e = corrected[ci]
                corrected[ci] = (round(s - last_drift, 3), round(e - last_drift, 3))

        return corrected

    def _build_punct_to_raw_map(
        self,
        punctuated_text: str,
        raw_text: str,
    ) -> List[int]:
        """建立 punctuated_text → raw_text 的位置映射。

        处理标点插入、空格差异、大小写差异。
        """
        punct_to_raw: List[int] = []
        punctuation_chars = set("，。！？；、：,.!?;:")
        raw_idx = 0
        punct_idx = 0

        while punct_idx < len(punctuated_text):
            p_ch = punctuated_text[punct_idx]

            if p_ch.isspace():
                punct_to_raw.append(raw_idx if raw_idx < len(raw_text) else -1)
                punct_idx += 1
                continue

            if p_ch in punctuation_chars:
                punct_to_raw.append(raw_idx if raw_idx < len(raw_text) else -1)
                punct_idx += 1
                continue

            if raw_idx < len(raw_text):
                r_ch = raw_text[raw_idx]
                if p_ch == r_ch or p_ch.lower() == r_ch.lower():
                    punct_to_raw.append(raw_idx)
                    raw_idx += 1
                    punct_idx += 1
                    continue

                # raw_text has a space that punctuated_text doesn't;
                # advance raw_idx only (punct_idx stays), loop is bounded
                # because raw_idx increases monotonically toward len(raw_text)
                if r_ch.isspace():
                    raw_idx += 1
                    continue

                # punctuated_text has a char that raw_text skips
                found_ahead = -1
                for ahead in range(1, 5):
                    if raw_idx + ahead < len(raw_text) and (
                        punctuated_text[punct_idx] == raw_text[raw_idx + ahead]
                        or punctuated_text[punct_idx].lower() == raw_text[raw_idx + ahead].lower()
                    ):
                        found_ahead = raw_idx + ahead
                        break
                if found_ahead >= 0:
                    punct_to_raw.append(found_ahead)
                    raw_idx = found_ahead + 1
                    punct_idx += 1
                    continue

                punct_to_raw.append(raw_idx)
                raw_idx += 1
                punct_idx += 1
            else:
                punct_to_raw.append(-1)
                punct_idx += 1

        return punct_to_raw

    def _build_raw_to_seg_map(
        self, raw_text: str, seg_text: str, seg_start_in_raw: int,
    ) -> List[int]:
        """建立 raw_text → seg_text 的位置映射。

        raw_text 和 seg_text 可能有空格差异，
        返回列表中 raw_to_seg[i] = seg_text 中对应的位置（raw_start_in_seg + offset）。
        """
        raw_to_seg = [-1] * len(raw_text)
        seg_idx = 0
        ri = seg_start_in_raw

        while ri < len(raw_text) and seg_idx < len(seg_text):
            r_ch = raw_text[ri]
            s_ch = seg_text[seg_idx]
            if r_ch == s_ch or r_ch.lower() == s_ch.lower():
                raw_to_seg[ri] = seg_idx
                seg_idx += 1
                ri += 1
            elif r_ch == " ":
                ri += 1
            elif s_ch == " ":
                seg_idx += 1
            else:
                raw_to_seg[ri] = seg_idx
                seg_idx += 1
                ri += 1

        return raw_to_seg

    def _split_vad_segment_at_punctuation(
        self,
        seg_text: str,
        seg_start_in_raw: int,
        seg_end_in_raw: int,
        vad_start: float,
        vad_end: float,
        punctuated_text: str,
        punct_to_raw: List[int],
        char_time_map: List[Tuple[float, float]],
        max_chars: int,
        raw_text: str = "",
    ) -> List[TranscriptionSegment]:
        """在标点位置切分过长的 VAD 分段。"""
        sentence_ends = set("。！？!?.")
        clause_ends = set("，,；;：:")

        # 建立 raw_text → seg_text 和 seg_text → raw_text 的位置映射
        raw_to_seg = self._build_raw_to_seg_map(raw_text, seg_text, seg_start_in_raw)
        # 反向映射: seg_text offset → raw_text offset
        seg_to_raw = {}
        for ri, si in enumerate(raw_to_seg):
            if si >= 0:
                seg_to_raw[si] = ri

        split_offsets: List[int] = []

        for punct_idx in range(len(punctuated_text)):
            if punct_idx >= len(punct_to_raw):
                break
            raw_pos = punct_to_raw[punct_idx]
            if raw_pos < 0 or raw_pos < seg_start_in_raw or raw_pos >= seg_end_in_raw:
                continue

            ch = punctuated_text[punct_idx]
            seg_pos = raw_to_seg[raw_pos] if raw_pos < len(raw_to_seg) else -1
            if seg_pos < 0:
                continue

            if ch in sentence_ends:
                split_offsets.append(seg_pos)
            elif ch in clause_ends:
                last_split = split_offsets[-1] if split_offsets else 0
                left_len = seg_pos - last_split
                right_len = len(seg_text) - seg_pos
                if left_len >= 6 and right_len >= 6:
                    split_offsets.append(seg_pos)

        if not split_offsets:
            split_offsets = self._find_chinese_natural_breaks(seg_text, max_chars)

        # 将 seg_text 坐标的 split_offsets 转换回 raw_text 坐标
        raw_split_offsets = []
        for so in split_offsets:
            if so in seg_to_raw:
                raw_split_offsets.append(seg_to_raw[so])
            else:
                for delta in range(0, 5):
                    if so + delta in seg_to_raw:
                        raw_split_offsets.append(seg_to_raw[so + delta])
                        break
                    if so - delta in seg_to_raw and so - delta >= 0:
                        raw_split_offsets.append(seg_to_raw[so - delta])
                        break

        sub_segments = self._create_sub_segments(
            seg_text, split_offsets, vad_start, vad_end,
            seg_start_in_raw, char_time_map,
            raw_split_offsets=raw_split_offsets,
        )
        sub_segments = self._fix_segments_crossing_silence(
            sub_segments, seg_start_in_raw, char_time_map, min_gap=2.0,
            seg_text=seg_text, seg_to_raw=seg_to_raw,
        )
        return sub_segments

    def _strip_punctuation(self, text: str) -> str:
        punct = set("，。！？；：、,.!?;:""")
        s = text
        while s and s[0] in punct:
            s = s[1:]
        while s and s[-1] in punct:
            s = s[:-1]
        return s

    def _find_in_raw_text(
        self, raw_text: str, piece: str, start_pos: int,
    ) -> int:
        """在 raw_text 中查找 piece 的位置，容许空格差异"""
        pos = raw_text.find(piece, start_pos)
        if pos >= 0:
            return pos
        clean_piece = piece.replace(" ", "").lower()
        mapping = []
        clean_chars = []
        for i, ch in enumerate(raw_text):
            if ch != " ":
                mapping.append(i)
                clean_chars.append(ch.lower())
        clean_raw = "".join(clean_chars)
        offset = clean_raw.find(clean_piece, 0)
        if offset >= 0:
            actual_pos = mapping[offset]
            if actual_pos >= start_pos:
                return actual_pos
        return -1

    def _locate_seg_in_punctuated(
        self,
        punctuated_text: str,
        seg_text: str,
        seg_start_in_raw: int,
        punct_to_raw: List[int],
    ) -> Tuple[int, int]:
        """在 punctuated_text 中定位 seg_text 对应的起止位置（含标点）。

        使用 punct_to_raw 找到 seg_start_in_raw 对应的 punctuated_text 起始位置，
        然后找到对应的结束位置。
        """
        punct_start = -1
        punct_end = len(punctuated_text)

        for pi, ri in enumerate(punct_to_raw):
            if ri == seg_start_in_raw and punct_start < 0:
                punct_start = pi
            if ri >= seg_start_in_raw + len(seg_text) and punct_start >= 0:
                punct_end = pi
                break

        if punct_start < 0:
            clean_seg = seg_text.replace(" ", "").lower()
            clean_punct = punctuated_text.replace(" ", "").lower()
            idx = clean_punct.find(clean_seg)
            if idx >= 0:
                punct_start = idx
                punct_end = idx + len(seg_text) + 10
            else:
                punct_start = 0
                punct_end = len(punctuated_text)

        return punct_start, punct_end

    def _fix_segments_crossing_silence(
        self,
        segments: List[TranscriptionSegment],
        seg_start_in_raw: int,
        char_time_map: List[Tuple[float, float]],
        min_gap: float = 2.0,
        seg_text: str = "",
        seg_to_raw: dict = None,
    ) -> List[TranscriptionSegment]:
        """修正跨静音间隙的 segment 时间戳，但不拆断文本。"""
        if not segments or not char_time_map:
            return segments

        char_offset_in_seg = 0
        for i, seg in enumerate(segments):
            seg_len = len(seg.text)
            if seg_to_raw:
                raw_start = seg_to_raw.get(char_offset_in_seg, seg_start_in_raw + char_offset_in_seg)
            else:
                raw_start = seg_start_in_raw + char_offset_in_seg

            new_end_time = seg.end_time
            for raw_ci in range(raw_start + 1, raw_start + seg_len + 5):
                if raw_ci >= len(char_time_map):
                    break
                gap = char_time_map[raw_ci][0] - char_time_map[raw_ci - 1][1]
                if gap > min_gap:
                    new_end_time = round(char_time_map[raw_ci - 1][1], 3)
                    if new_end_time <= seg.start_time:
                        new_end_time = round(seg.start_time + 0.1, 3)
                    break

            if new_end_time != seg.end_time:
                segments[i] = seg.copy(update={"end_time": new_end_time})
            char_offset_in_seg += seg_len

        return segments

    def _find_silence_split_offsets(
        self,
        seg_text: str,
        seg_start_in_raw: int,
        char_time_map: List[Tuple[float, float]],
        min_gap: float = 2.0,
    ) -> List[int]:
        """在 char_time_map 中的静音间隙处寻找切分位置"""
        splits = []
        for i in range(1, len(seg_text)):
            cur_idx = seg_start_in_raw + i
            prev_idx = seg_start_in_raw + i - 1
            if cur_idx >= len(char_time_map) or prev_idx >= len(char_time_map):
                break
            gap = char_time_map[cur_idx][0] - char_time_map[prev_idx][1]
            if gap > min_gap:
                splits.append(i)
        return splits

    def _find_chinese_natural_breaks(
        self,
        text: str,
        max_chars: int,
    ) -> List[int]:
        """在中文文本中寻找自然断句点（助词、连词处）"""
        breaks: List[int] = []
        last_break = 0

        for i, ch in enumerate(text):
            if i - last_break < max_chars:
                continue
            # 距上次切分已超过 max_chars，寻找附近的断点
            for j in range(i, min(i + 8, len(text))):
                if text[j] in "的了呢吧啊吗着过地得":
                    breaks.append(j + 1)  # 在助词后切分
                    last_break = j + 1
                    break
            else:
                # 没有找到助词，强制在当前位置切分
                breaks.append(i)
                last_break = i

        return breaks

    def _create_sub_segments(
        self,
        text: str,
        split_offsets: List[int],
        vad_start: float,
        vad_end: float,
        seg_start_in_raw: int,
        char_time_map: List[Tuple[float, float]],
        raw_split_offsets: List[int] = None,
    ) -> List[TranscriptionSegment]:
        """根据切分点创建子分段。

        split_offsets: 文本切分位置（seg_text 坐标）
        raw_split_offsets: 对应的 raw_text 坐标（用于 char_time_map 索引）
        """
        if not split_offsets:
            return [TranscriptionSegment(
                start_time=vad_start,
                end_time=vad_end,
                text=text.strip(),
                confidence=0.95,
            )]

        use_raw = raw_split_offsets and len(raw_split_offsets) == len(split_offsets)

        segments: List[TranscriptionSegment] = []
        prev_offset = 0
        prev_raw_offset = seg_start_in_raw

        for i, offset in enumerate(split_offsets):
            sub_text = text[prev_offset:offset].strip()
            if not sub_text:
                prev_offset = offset
                if use_raw:
                    prev_raw_offset = raw_split_offsets[i]
                continue

            if use_raw:
                start_idx = prev_raw_offset
                end_idx = raw_split_offsets[i] - 1
            else:
                start_idx = seg_start_in_raw + prev_offset
                end_idx = seg_start_in_raw + offset - 1

            t_start = char_time_map[start_idx][0] if start_idx < len(char_time_map) else vad_start
            t_end = char_time_map[end_idx][1] if 0 <= end_idx < len(char_time_map) else vad_end

            if t_end <= t_start:
                t_end = t_start + 0.1

            seg_start = round(t_start, 3)
            seg_end = max(round(t_end, 3), seg_start + 0.001)
            segments.append(TranscriptionSegment(
                start_time=seg_start,
                end_time=seg_end,
                text=sub_text,
                confidence=0.95,
            ))
            prev_offset = offset
            if use_raw:
                prev_raw_offset = raw_split_offsets[i]

        # 处理剩余部分
        remaining = text[prev_offset:].strip()
        if remaining:
            if use_raw and raw_split_offsets:
                start_idx = prev_raw_offset
            else:
                start_idx = seg_start_in_raw + prev_offset
            t_start = char_time_map[start_idx][0] if start_idx < len(char_time_map) else vad_start
            seg_start = round(t_start, 3)
            seg_end = max(round(vad_end, 3), seg_start + 0.001)
            segments.append(TranscriptionSegment(
                start_time=seg_start,
                end_time=seg_end,
                text=remaining,
                confidence=0.95,
            ))

        return segments

    def _build_segments_by_punctuation_then_align(
        self,
        raw_text: str,
        punctuated_text: str,
        char_timestamps: List[CharTimestamp],
    ) -> List[TranscriptionSegment]:
        """
        核心流程：标点断句 → 去标点 → 时间戳对齐

        策略：
        1. 建立 punctuated_text → raw_text 的字符位置映射
        2. 在 punctuated_text 中找到标点位置
        3. 通过映射找到对应的 raw_text 位置
        4. 从 raw_text 中提取句子（不含标点）
        5. 为每个句子分配时间戳
        """
        if not raw_text or not char_timestamps:
            return []

        # 步骤1: 建立 raw_text 每个字符的时间
        expanded_ts = self._expand_subtitle_char_timestamps([
            ts for ts in char_timestamps if ts.word and ts.end >= ts.start
        ])
        if not expanded_ts:
            logger.warning("_build_segments_by_punctuation_then_align: expanded_ts 为空")
            return []

        # 建立 raw_text 每个字符的时间
        # 如果 char_timestamps 的字符数少于 raw_text，需要填充
        raw_char_times: List[Tuple[float, float]] = []
        for ts in expanded_ts:
            n_chars = len(ts.word)
            if n_chars == 1:
                raw_char_times.append((ts.start, ts.end))
            else:
                dur = (ts.end - ts.start) / n_chars
                for i in range(n_chars):
                    raw_char_times.append((
                        round(ts.start + dur * i, 3),
                        round(ts.start + dur * (i + 1), 3),
                    ))

        # 如果 raw_char_times 数量少于 raw_text，用最后一个时间填充
        while len(raw_char_times) < len(raw_text):
            if raw_char_times:
                last_time = raw_char_times[-1]
                raw_char_times.append((last_time[1], last_time[1] + 0.1))
            else:
                raw_char_times.append((0.0, 0.1))

        # 如果 raw_char_times 为空，直接返回空
        if not raw_char_times:
            logger.warning("_build_segments_by_punctuation_then_align: raw_char_times 为空")
            return []

        logger.info(f"_build_segments_by_punctuation_then_align: "
                   f"raw_text 长度={len(raw_text)}, "
                   f"raw_char_times 数量={len(raw_char_times)}, "
                   f"第一个时间={raw_char_times[0] if raw_char_times else 'N/A'}, "
                   f"最后一个时间={raw_char_times[-1] if raw_char_times else 'N/A'}")

        # 步骤2: 建立 punctuated_text → raw_text 的位置映射
        punct_to_raw: List[int] = []  # punct_to_raw[i] = 对应的 raw_text 位置
        raw_idx = 0
        for ch in punctuated_text:
            if ch.isspace():
                punct_to_raw.append(-1)  # 空格不映射
                continue
            if raw_idx < len(raw_text):
                # 尝试匹配
                if raw_idx < len(raw_text) and ch == raw_text[raw_idx]:
                    punct_to_raw.append(raw_idx)
                    raw_idx += 1
                else:
                    # 尝试跳过少量字符
                    found = False
                    for ahead in range(1, 5):
                        if raw_idx + ahead < len(raw_text) and ch == raw_text[raw_idx + ahead]:
                            punct_to_raw.append(raw_idx + ahead)
                            raw_idx = raw_idx + ahead + 1
                            found = True
                            break
                    if not found:
                        punct_to_raw.append(raw_idx)
                        raw_idx += 1
            else:
                punct_to_raw.append(-1)

        # 步骤3: 在 punctuated_text 中找到标点位置（句子边界）
        sentence_ends = set("。！？!?.")
        clause_ends = set("，,；;：:")

        # 收集所有标点位置
        split_positions: List[Tuple[int, str]] = []
        for i, ch in enumerate(punctuated_text):
            if ch in sentence_ends:
                split_positions.append((i, "sentence"))
            elif ch in clause_ends:
                split_positions.append((i, "clause"))

        # 步骤4: 根据标点位置切分句子
        segments = []
        last_split_raw_pos = 0  # 上次切分在 raw_text 中的位置

        for punct_pos, split_type in split_positions:
            # 获取标点在 raw_text 中的位置
            if punct_pos >= len(punct_to_raw) or punct_to_raw[punct_pos] < 0:
                continue

            raw_pos = punct_to_raw[punct_pos]

            # 确定是否在此处切分
            should_split = False
            if split_type == "sentence":
                should_split = True  # 句末标点必断
            elif split_type == "clause":
                # 逗号：当句子够长时切分
                if raw_pos - last_split_raw_pos >= 8:
                    should_split = True

            if not should_split:
                continue

            # 提取句子文本（从 raw_text 中，不含标点）
            sent_text = raw_text[last_split_raw_pos:raw_pos]
            if not sent_text.strip():
                last_split_raw_pos = raw_pos
                continue

            # 获取时间范围
            t_start_idx = last_split_raw_pos
            t_end_idx = min(raw_pos - 1, len(raw_char_times) - 1)

            if t_start_idx < len(raw_char_times):
                t_start = raw_char_times[t_start_idx][0]
            else:
                t_start = 0.0

            if t_end_idx < len(raw_char_times) and t_end_idx >= t_start_idx:
                t_end = raw_char_times[t_end_idx][1]
            else:
                t_end = t_start + 0.1

            if t_end < t_start:
                t_end = t_start + 0.1

            # 超长句子拆分
            if len(sent_text) > 30:
                sub_segments = self._split_and_create_segments(
                    sent_text, t_start, t_end, raw_char_times, last_split_raw_pos
                )
                segments.extend(sub_segments)
            else:
                # 确保时间有效
                if t_end <= t_start:
                    t_end = t_start + 0.1
                segments.append(TranscriptionSegment(
                    start_time=round(t_start, 3),
                    end_time=round(t_end, 3),
                    text=sent_text.strip(),
                    confidence=0.95,
                ))

            last_split_raw_pos = raw_pos

        # 处理剩余内容
        if last_split_raw_pos < len(raw_text):
            remaining = raw_text[last_split_raw_pos:]
            if remaining.strip():
                t_start_idx = last_split_raw_pos
                t_end_idx = len(raw_char_times) - 1

                if t_start_idx < len(raw_char_times):
                    t_start = raw_char_times[t_start_idx][0]
                else:
                    t_start = 0.0

                if t_end_idx < len(raw_char_times):
                    t_end = raw_char_times[t_end_idx][1]
                else:
                    t_end = t_start + 0.1

                # 确保时间有效
                if t_end <= t_start:
                    t_end = t_start + 0.1

                if len(remaining) > 30:
                    sub_segments = self._split_and_create_segments(
                        remaining, t_start, t_end, raw_char_times, last_split_raw_pos
                    )
                    segments.extend(sub_segments)
                else:
                    segments.append(TranscriptionSegment(
                        start_time=round(t_start, 3),
                        end_time=round(t_end, 3),
                        text=remaining.strip(),
                        confidence=0.95,
                    ))

        # 步骤5: 修复时间重叠
        return self._dedupe_and_fix_segment_timing(segments)

    def _split_and_create_segments(
        self,
        text: str,
        t_start: float,
        t_end: float,
        raw_char_times: List[Tuple[float, float]],
        raw_offset: int,
    ) -> List[TranscriptionSegment]:
        """拆分超长中文句子并创建字幕片段"""
        segments = []
        duration = t_end - t_start
        text_len = len(text)

        # 寻找切分点（中文标点或助词）
        split_points = []
        for i, ch in enumerate(text):
            if ch in "，。！？；、：":
                split_points.append(i)

        if not split_points:
            mid = text_len // 2
            for i in range(mid - 5, mid + 5):
                if 0 < i < text_len and text[i] in "的了呢吧啊吗着过地得":
                    split_points.append(i)

        if not split_points:
            split_points = [text_len // 2]

        split_pos = split_points[0] + 1
        if split_pos <= 0:
            split_pos = max(1, text_len // 2)

        # 第一段
        seg1_text = text[:split_pos]
        if seg1_text.strip():
            t1_end = t_start + (duration * split_pos / text_len)
            if t1_end <= t_start:
                t1_end = t_start + 0.1
            segments.append(TranscriptionSegment(
                start_time=round(t_start, 3),
                end_time=round(t1_end, 3),
                text=seg1_text.strip(),
                confidence=0.95,
            ))

        # 第二段
        seg2_text = text[split_pos:]
        if seg2_text.strip():
            t2_start = t_start + (duration * split_pos / text_len)
            if t2_start >= t_end:
                t2_start = t_end - 0.1
            if t2_start < t_start:
                t2_start = t_start
            segments.append(TranscriptionSegment(
                start_time=round(t2_start, 3),
                end_time=round(t_end, 3),
                text=seg2_text.strip(),
                confidence=0.95,
            ))

        return segments

    def _build_subtitle_segments_from_raw_ts(
        self,
        char_timestamps: List[CharTimestamp],
        punctuated_text: str = "",
        max_chars: int = 36,
        max_duration: float = 8.0,
    ) -> List[TranscriptionSegment]:
        """
        基于标点符号构建字幕片段。

        核心策略：优先在标点处断句，保证断句自然。
        1. 句号/问号/感叹号 → 必断
        2. 逗号/分号 → 当片段超过 max_chars 的 60% 时断
        3. 超长片段 → 强制在最佳位置切分
        """
        valid_timestamps = self._expand_subtitle_char_timestamps([
            ts for ts in char_timestamps
            if ts.word and ts.end >= ts.start
        ])
        if not valid_timestamps:
            return []

        raw_text = "".join(ts.word for ts in valid_timestamps)

        # 建立标点位置映射（punctuated_text → raw_text 的位置）
        punct_positions = self._map_punctuation_positions(raw_text, punctuated_text)

        segments = []
        current: List[CharTimestamp] = []
        char_count = 0

        def flush(items: List[CharTimestamp]):
            text = "".join(ts.word for ts in items).strip()
            if text:
                segments.append(TranscriptionSegment(
                    start_time=round(items[0].start, 3),
                    end_time=round(items[-1].end, 3),
                    text=text,
                    confidence=0.95,
                    char_timestamps=list(items),
                ))

        for ts in valid_timestamps:
            current.append(ts)
            char_count += len(ts.word)

            # 检查是否应该在此处断句
            should_split = False
            split_reason = ""

            # 1. 句末标点（。！？!?）→ 必断
            if punct_positions.get(char_count) == "sentence_end":
                should_split = True
                split_reason = "句末标点"

            # 2. 逗号/分号（，,；;）→ 当片段够长时断
            elif punct_positions.get(char_count) == "clause_end":
                if char_count >= max_chars * 0.4:
                    should_split = True
                    split_reason = "从句标点"

            # 3. 片段过长 → 强制切分
            elif char_count > max_chars or (current[-1].end - current[0].start > max_duration):
                should_split = True
                split_reason = "超长切分"

            if should_split:
                # 超长切分时，找到最佳切分位置
                if split_reason == "超长切分":
                    split_idx = self._find_best_split_point(current, max_chars)
                    if split_idx > 0:
                        flush(current[:split_idx])
                        current = current[split_idx:]
                        char_count = sum(len(ts.word) for ts in current)
                    else:
                        flush(current)
                        current = []
                        char_count = 0
                else:
                    flush(current)
                    current = []
                    char_count = 0

        # 处理剩余内容
        if current:
            flush(current)

        # 合并过短片段并修复时间重叠
        return self._dedupe_and_fix_segment_timing(segments)

    def _build_segments_from_punctuation(
        self,
        punctuated_text: str,
        char_timestamps: List[CharTimestamp],
        max_chars: int = 20,
        max_duration: float = 5.0,
    ) -> List[TranscriptionSegment]:
        """
        基于标点断句 + 时间戳对齐。

        流程：
        1. 按标点将文本切分为句子
        2. 建立字符位置 → 时间的映射
        3. 为每个句子查找精确的开始/结束时间
        4. 合并过短句子，拆分超长句子
        """
        if not punctuated_text or not char_timestamps:
            return []

        # 步骤1: 按标点切分句子
        sentences = self._split_sentences_by_punctuation(punctuated_text)
        if not sentences:
            return []

        # 步骤2: 建立字符 → 时间映射
        expanded_ts = self._expand_subtitle_char_timestamps([
            ts for ts in char_timestamps if ts.word and ts.end >= ts.start
        ])
        if not expanded_ts:
            return []

        raw_text = "".join(ts.word for ts in expanded_ts)
        char_time_map = self._build_char_time_map(expanded_ts, raw_text, punctuated_text)

        # 步骤3: 为每个句子分配时间
        segments = []
        for sent_text, sent_start_char, sent_end_char in sentences:
            if not sent_text.strip():
                continue

            # 查找句子的时间范围
            t_start = char_time_map.get(sent_start_char, (0.0, 0.0))[0]
            t_end = char_time_map.get(sent_end_char - 1, (0.0, 0.0))[1]

            if t_end <= t_start:
                t_end = t_start + 0.1

            # 超长句子拆分
            if len(sent_text) > max_chars or t_end - t_start > max_duration:
                sub_segments = self._split_long_sentence(
                    sent_text, t_start, t_end, max_chars, max_duration
                )
                segments.extend(sub_segments)
            else:
                segments.append(TranscriptionSegment(
                    start_time=round(t_start, 3),
                    end_time=round(t_end, 3),
                    text=sent_text.strip(),
                    confidence=0.95,
                ))

        # 步骤4: 合并过短 + 修复重叠
        return self._dedupe_and_fix_segment_timing(segments)

    def _split_sentences_by_punctuation(
        self, text: str, min_clause_len: int = 8
    ) -> List[Tuple[str, int, int]]:
        """
        按标点切分句子。

        Returns:
            List[(sentence_text, start_char_pos, end_char_pos)]
        """
        sentence_ends = set("。！？!?.")
        clause_ends = set("，,；;：:")

        sentences = []
        current_start = 0
        i = 0

        while i < len(text):
            ch = text[i]

            # 句末标点 → 必断
            if ch in sentence_ends:
                sent_text = text[current_start:i + 1]
                if sent_text.strip():
                    sentences.append((sent_text, current_start, i + 1))
                current_start = i + 1

            # 从句标点 → 当句子够长时断
            elif ch in clause_ends:
                sent_len = i - current_start
                if sent_len >= min_clause_len:
                    sent_text = text[current_start:i + 1]
                    if sent_text.strip():
                        sentences.append((sent_text, current_start, i + 1))
                    current_start = i + 1

            i += 1

        # 处理剩余内容
        if current_start < len(text):
            remaining = text[current_start:]
            if remaining.strip():
                sentences.append((remaining, current_start, len(text)))

        return sentences

    def _build_char_time_map(
        self,
        expanded_ts: List[CharTimestamp],
        raw_text: str,
        punctuated_text: str,
    ) -> Dict[int, Tuple[float, float]]:
        """
        建立 punctuated_text 字符位置 → (start, end) 的映射。

        通过字符匹配将 punctuated_text 的位置映射到 raw_text，
        再从 expanded_ts 获取时间。
        """
        time_map: Dict[int, Tuple[float, float]] = {}

        # 先建立 raw_text 位置 → 时间
        raw_time_map: Dict[int, Tuple[float, float]] = {}
        for i, ts in enumerate(expanded_ts):
            raw_time_map[i] = (ts.start, ts.end)

        # 建立 punctuated_text → raw_text 的位置映射
        raw_idx = 0
        for punct_idx, ch in enumerate(punctuated_text):
            if ch.isspace():
                continue
            if raw_idx < len(raw_text):
                pos = raw_text.find(ch, raw_idx, min(raw_idx + 5, len(raw_text)))
                if pos != -1:
                    if pos in raw_time_map:
                        time_map[punct_idx] = raw_time_map[pos]
                    raw_idx = pos + 1
                else:
                    raw_idx += 1

        return time_map

    def _split_long_sentence(
        self,
        text: str,
        t_start: float,
        t_end: float,
        max_chars: int,
        max_duration: float,
    ) -> List[TranscriptionSegment]:
        """拆分超长句子为多个字幕片段。"""
        segments = []
        duration = t_end - t_start

        # 按字符数估算切分次数
        n_splits = max(1, (len(text) + max_chars - 1) // max_chars)
        char_per_split = len(text) // n_splits

        current_pos = 0
        for i in range(n_splits):
            if i == n_splits - 1:
                # 最后一段：取剩余所有内容
                seg_text = text[current_pos:]
                seg_end = t_end
            else:
                # 寻找自然切分点（标点或单词边界）
                target_pos = min(current_pos + char_per_split, len(text) - 1)
                split_pos = self._find_natural_split(text, current_pos, target_pos)
                seg_text = text[current_pos:split_pos]
                seg_end = t_start + (duration * split_pos / len(text))

            if seg_text.strip():
                seg_start = t_start + (duration * current_pos / len(text))
                segments.append(TranscriptionSegment(
                    start_time=round(seg_start, 3),
                    end_time=round(seg_end, 3),
                    text=seg_text.strip(),
                    confidence=0.95,
                ))

            current_pos = split_pos if i < n_splits - 1 else len(text)

        return segments

    def _find_natural_split(self, text: str, start: int, target: int) -> int:
        """在 target 附近寻找自然切分点（标点或单词边界）。"""
        # 向后搜索标点
        for i in range(target, min(target + 10, len(text))):
            if text[i] in "，,。！？!?;；:：":
                return i + 1

        # 向前搜索标点
        for i in range(target, max(start, target - 10), -1):
            if text[i] in "，,。！？!?;；:：":
                return i + 1

        # 英文单词边界
        if target < len(text) and text[target] == ' ':
            return target + 1

        # 没找到好的切分点，就在 target 处切
        return max(start + 1, target)

    def _map_punctuation_positions(
        self, raw_text: str, punctuated_text: str
    ) -> Dict[int, str]:
        """
        映射标点在 raw_text 中的位置。

        Returns:
            Dict[int, str]: {位置: "sentence_end" | "clause_end"}
        """
        positions: Dict[int, str] = {}
        if not raw_text or not punctuated_text:
            return positions

        sentence_ends = set("。！？!?.")
        clause_ends = set("，,；;：:")

        raw_idx = 0
        for ch in punctuated_text:
            if ch in sentence_ends:
                if raw_idx > 0:
                    positions[raw_idx] = "sentence_end"
                continue
            if ch in clause_ends:
                if raw_idx > 0:
                    positions[raw_idx] = "clause_end"
                continue
            if ch.isspace():
                continue
            if raw_idx < len(raw_text):
                # 尝试匹配 raw_text 中的字符
                pos = raw_text.find(ch, raw_idx, min(raw_idx + 5, len(raw_text)))
                if pos != -1:
                    raw_idx = pos + 1
                else:
                    raw_idx += 1

        return positions

    def _find_best_split_point(
        self, items: List[CharTimestamp], max_chars: int
    ) -> int:
        """
        在超长无标点片段中找到最佳切分位置。

        优先级：
        1. 英文单词边界（空格位置）
        2. 中文助词/语气词后
        3. max_chars 的 60-80% 范围内
        """
        if len(items) <= 1:
            return 0

        text = "".join(ts.word for ts in items)
        total_len = len(text)

        # 目标切分范围：max_chars 的 60-80%
        target_start = int(max_chars * 0.6)
        target_end = min(int(max_chars * 0.8), total_len - 1)

        if target_start >= target_end:
            target_start = max_chars // 2

        best_pos = 0
        best_score = 0
        char_pos = 0

        for i, ts in enumerate(items[:-1], 1):
            char_pos += len(ts.word)

            if char_pos < target_start:
                continue
            if char_pos > target_end:
                break

            score = 0
            prev_char = text[char_pos - 1] if char_pos > 0 else ""
            next_char = text[char_pos] if char_pos < total_len else ""

            # 英文单词边界
            if prev_char.isascii() and next_char.isascii():
                if prev_char.isalpha() and next_char.isalpha():
                    continue  # 英文单词中间不切
                if prev_char.isalpha() and not next_char.isalpha():
                    score += 30  # 英文单词结尾
                if not prev_char.isalpha() and next_char.isalpha():
                    score += 20  # 英文单词开头

            # 中文助词后
            if prev_char in "的了呢吧啊吗着过":
                score += 25

            # 中文语气词前
            if next_char in "那么但是而且所以因为然后":
                score += 20

            # 偏好更接近 max_chars 的 70% 处
            distance_from_70 = abs(char_pos - int(max_chars * 0.7))
            score += max(0, 10 - distance_from_70 // 2)

            if score > best_score:
                best_score = score
                best_pos = i

        # 如果没找到好的切分点，就在中间切
        if best_pos == 0:
            best_pos = max(1, len(items) // 2)

        return best_pos

    def _expand_subtitle_char_timestamps(
        self,
        char_timestamps: List[CharTimestamp],
    ) -> List[CharTimestamp]:
        if expand_char_timestamps_syllable_aware is not None:
            return expand_char_timestamps_syllable_aware(char_timestamps)

        expanded = []
        for ts in char_timestamps:
            text = ts.word.strip()
            if not text:
                continue
            if len(text) == 1 or ts.end <= ts.start:
                expanded.append(ts)
                continue

            duration = ts.end - ts.start
            char_duration = duration / len(text)
            for index, ch in enumerate(text):
                start_time = ts.start + char_duration * index
                end_time = ts.start + char_duration * (index + 1)
                expanded.append(CharTimestamp(
                    word=ch,
                    start=round(start_time, 3),
                    end=round(end_time, 3),
                ))
        return expanded

    def _is_safe_subtitle_boundary(self, text: str, pos: int) -> bool:
        """
        中文安全边界检测。

        规则:
        1. 不能在助词（的/了/呢/吧/啊/吗/着/过）之前断开
        2. 不能在介词/连词（但/和/与/及/把/被/对/在/以/从/向/给）之后断开
        """
        if pos <= 0 or pos >= len(text):
            return True

        prev_char = text[pos - 1]
        next_char = text[pos]

        # 中文助词不作为下一行的开头
        if next_char in "的呢吧啊吗着过了":
            return False

        # 介词/连词不作为上一行的结尾
        if prev_char in "但和与及把被对在以从向给":
            return False

        return True

    def _subtitle_split_points_from_punctuation(
        self,
        raw_text: str,
        punctuated_text: str,
        min_chars: int = 8,
    ) -> set[int]:
        if not raw_text or not punctuated_text:
            return set()

        strong_punct = set("。！？!?")
        soft_punct = set("，,；;：:")
        split_points = set()
        raw_idx = 0
        last_split = 0

        for ch in punctuated_text:
            if ch in strong_punct | soft_punct:
                if raw_idx - last_split >= min_chars:
                    split_points.add(raw_idx)
                    last_split = raw_idx
                continue
            if ch.isspace():
                continue
            if raw_idx >= len(raw_text):
                break

            pos = raw_text.find(ch, raw_idx, min(raw_idx + 8, len(raw_text)))
            if pos == -1:
                pos = raw_idx
            raw_idx = pos + 1

        return split_points

    def _subtitle_split_points_from_text(self, raw_text: str) -> set[int]:
        """
        通用文本分割点检测。

        基于通用语言学规则而非硬编码词组列表:
        1. 检测转折/因果连接词（通用模式）
        2. 检测序数词/列举词
        3. 检测总结/转折词
        """
        split_points = set()

        # 通用连接词模式（可出现在句子开头，适合作为切分点）
        connector_patterns = [
            r'那么(?=[，,]|\s)',
            r'但是(?=[，,]|\s|.)',
            r'而且(?=[，,]|\s)',
            r'所以(?=[，,]|\s)',
            r'因为(?=[，,]|\s)',
            r'然后(?=[，,]|\s)',
            r'接下来(?=[，,]|\s)',
            r'另外(?=[，,]|\s)',
            r'同时(?=[，,]|\s)',
            r'首先(?=[，,]|\s)',
            r'其次(?=[，,]|\s)',
            r'最后(?=[，,]|\s)',
            r'第[一二三四五六七八九十\d]+[，,]?',
            r'当然(?=[，,]|\s|了)',
            r'比如说(?=[，,]|\s)',
            r'实际上(?=[，,]|\s)',
            r'总体(?:上)?(?:而言)?(?=[，,]。\s])',
            r'大家(?:都)?知道(?=[，,]|\s)',
        ]

        for pattern in connector_patterns:
            for m in re.finditer(pattern, raw_text):
                pos = m.start()
                if pos >= 8:
                    split_points.add(pos)

        # 英文空格位置也是合理分割点（英文单词边界）
        for i, ch in enumerate(raw_text):
            if ch == ' ' and i >= 8 and i < len(raw_text) - 8:
                # 检查两边是否都是英文
                if i > 0 and raw_text[i-1].isascii() and i+1 < len(raw_text) and raw_text[i+1].isascii():
                    split_points.add(i + 1)

        return split_points

    def _best_subtitle_split_index(
        self,
        items: List[CharTimestamp],
        min_chars: int,
        max_chars: int,
        force_split: bool = False,
        max_duration: float = 8.0,
    ) -> int:
        """
        通用字幕最佳切分点选择。

        评分因素（按权重排序）:
        1. 音频停顿位置 (score += 500) — 最强信号
        2. 时间间隙 (gap * 100)
        3. 连接词/转折词位置 (score += 100)
        4. 中文句末字 (score += 10)
        5. 字符位置偏好 (靠近 max_chars 的 65% 处加分)
        """
        text = "".join(ts.word for ts in items)
        if len(text) <= max_chars and not force_split:
            return 0

        split_positions = []
        char_pos = 0
        for i, ts in enumerate(items[:-1], 1):
            char_pos += len(ts.word)
            split_positions.append((i, char_pos))

        def safe_split_candidates(lower_bound: int = 1, upper_bound: Optional[int] = None):
            if upper_bound is None:
                upper_bound = len(text) - 1
            return [
                (i, pos)
                for i, pos in split_positions
                if lower_bound <= pos <= upper_bound and self._is_safe_subtitle_boundary(text, pos)
            ]

        if force_split and items[-1].end - items[0].start > max_duration:
            target_end = items[0].start + max_duration
            target_index = len(items) - 1
            for i, ts in enumerate(items[:-1], 1):
                if ts.end >= target_end:
                    target_index = i
                    break

            candidates = safe_split_candidates()
            if candidates:
                return min(
                    candidates,
                    key=lambda candidate: (
                        abs(items[candidate[0] - 1].end - target_end),
                        candidate[0] < target_index,
                    ),
                )[0]

        lower = min(min_chars, max(1, len(text) - 1))
        upper = min(max_chars, len(text) - min_chars)
        if force_split and upper <= lower:
            upper = max(lower, len(text) - 1)
        if upper <= lower:
            return max(1, min(max_chars, len(items) - 1))

        candidates = []
        phrase_points = self._subtitle_split_points_from_text(text)
        prev_char_pos = 0
        char_pos = 0
        for i, ts in enumerate(items[:-1], 1):
            prev_char_pos = char_pos
            char_pos += len(ts.word)
            if lower <= char_pos <= upper:
                if not self._is_safe_subtitle_boundary(text, char_pos):
                    continue

                # 基础分: 时间间隙
                gap = items[i].start - ts.end
                score = gap * 100

                # 连接词/转折词位置
                if any(prev_char_pos < point <= char_pos + 2 for point in phrase_points):
                    score += 100

                # 音频停顿位置（最强信号）
                split_time = (ts.end + items[i].start) / 2
                for silence_start, silence_end in self.silence_ranges:
                    silence_center = (silence_start + silence_end) / 2
                    if abs(split_time - silence_center) <= 0.5:
                        score += 500
                        break

                # 中文句末字（的了呢啊吧吗）
                prev_word = ts.word[-1]
                if prev_word in "的了呢啊吧吗":
                    score += 10
                # 标点符号后
                if prev_word in "，。！？,!?;；:：":
                    score += 15

                # 字符位置偏好
                if char_pos >= max_chars * 0.65:
                    score += 2

                candidates.append((score, i))

        if candidates:
            return max(candidates)[1]

        char_pos = 0
        for i, ts in enumerate(items[:-1], 1):
            char_pos += len(ts.word)
            if char_pos >= max_chars and self._is_safe_subtitle_boundary(text, char_pos):
                return i

        candidates = safe_split_candidates()
        if candidates:
            target_pos = min(max_chars, max(1, len(text) - 1))
            return min(candidates, key=lambda candidate: abs(candidate[1] - target_pos))[0]

        return max(1, len(items) - 1)

    def _dedupe_and_fix_segment_timing(
        self,
        segments: List[TranscriptionSegment],
        subtitle_hold_seconds: float = 0.35,
    ) -> List[TranscriptionSegment]:
        cleaned, overlap_fixed = fix_subtitle_segment_timing(
            segments,
            subtitle_hold_seconds=subtitle_hold_seconds,
        )

        if overlap_fixed:
            logger.info(f"修复 {overlap_fixed} 处字幕时间重叠")

        logger.info(f"基于原始时间戳构建 {len(cleaned)} 个字幕 segments")
        return cleaned

    def _build_segments_from_char_ts(
        self,
        char_timestamps: List[CharTimestamp],
        punctuated_text: str,
    ) -> List[TranscriptionSegment]:
        """
        从 char_timestamps 和带标点的文本构建 segments。

        关键: char_timestamps[i].word 可能是多字符 (如 "assistant")，
        所以 raw_text 有 N 个字符但只有 M 个 timestamp (N > M)。
        必须先建立 字符位置→时间 的映射，再查找。
        """
        if not char_timestamps:
            return []

        # ---- 第0步: 建立 raw_text 每个字符位置 → 时间的映射 ----
        char_time_map = []
        for ts in char_timestamps:
            for _ in range(len(ts.word)):
                char_time_map.append((ts.start, ts.end))

        raw_text = "".join(ts.word for ts in char_timestamps)
        total_chars = len(raw_text)

        if total_chars == 0:
            t_start = char_timestamps[0].start
            t_end = char_timestamps[-1].end
            if t_end <= t_start:
                t_end = t_start + 0.1
            return [TranscriptionSegment(
                start_time=t_start,
                end_time=t_end,
                text=punctuated_text.strip(),
                confidence=0.95,
            )]

        def char_pos_to_time(pos: int):
            pos = max(0, min(pos, total_chars - 1))
            return char_time_map[pos]

        # ---- 第1步: 建立 punctuated_text -> raw_text 字符位置映射 ----
        #    带前向搜索（标点模型可能插入字符）和比例回退（标点模型修改文本时）
        punct_to_char = []
        char_idx = 0

        for i, ch in enumerate(punctuated_text):
            if char_idx < total_chars and ch == raw_text[char_idx]:
                punct_to_char.append(char_idx)
                char_idx += 1
            else:
                # 前向搜索: 标点模型可能插入了字符，跳过 raw_text 中少量不匹配字符
                found = False
                for ahead in range(1, 6):
                    pos = char_idx + ahead
                    if pos < total_chars and ch == raw_text[pos]:
                        punct_to_char.append(pos)
                        char_idx = pos + 1
                        found = True
                        break
                if not found:
                    punct_to_char.append(min(char_idx, total_chars - 1))

        # 对齐质量检查: 若匹配率 < 80%，回退到比例映射
        aligned_count = char_idx
        if total_chars > 0 and aligned_count < total_chars * 0.8:
            logger.warning(
                f"标点文本与原始文本对齐率低: {aligned_count}/{total_chars} "
                f"({aligned_count / total_chars * 100:.1f}%)，回退到比例时间映射"
            )
            punct_len = max(len(punctuated_text) - 1, 1)
            punct_to_char = [
                min(int(total_chars * i / punct_len), total_chars - 1)
                for i in range(len(punctuated_text))
            ]

        # ---- 第2步: 按标点切分句子 ----
        sent_enders = set("。！？，；.!?;,\n")
        sentence_spans = []
        buf_start = 0
        for i, ch in enumerate(punctuated_text):
            if ch in sent_enders:
                if i + 1 > buf_start:
                    sentence_spans.append((buf_start, i + 1))
                buf_start = i + 1
            elif i == len(punctuated_text) - 1 and i + 1 > buf_start:
                sentence_spans.append((buf_start, i + 1))

        if not sentence_spans:
            sentence_spans = [(0, len(punctuated_text))]

        # ---- 第3步: 用精确时间构建 segments ----
        segments = []
        for (s_start, s_end) in sentence_spans:
            sent_text = punctuated_text[s_start:s_end].strip()
            if not sent_text:
                continue

            c_start = punct_to_char[min(s_start, len(punct_to_char) - 1)]
            c_end = punct_to_char[min(s_end - 1, len(punct_to_char) - 1)]

            t_start, _ = char_pos_to_time(c_start)
            _, t_end = char_pos_to_time(c_end)

            if t_end <= t_start:
                t_end = t_start + 0.1

            segments.append(TranscriptionSegment(
                start_time=round(t_start, 3),
                end_time=round(t_end, 3),
                text=sent_text,
                confidence=0.95,
            ))

        # ---- 第4步: 合并过短的 segments ----
        merged = []
        for seg in segments:
            if merged and len(self._SEGMENT_PUNCT_RE.sub('', seg.text)) < 4:
                new_end = max(seg.end_time, merged[-1].end_time)
                if new_end <= merged[-1].start_time:
                    new_end = merged[-1].start_time + 0.1
                merged[-1] = TranscriptionSegment(
                    start_time=merged[-1].start_time,
                    end_time=new_end,
                    text=merged[-1].text + seg.text,
                    confidence=0.95,
                )
            else:
                merged.append(seg)

        # ---- 第5步: 严格保证时间单调递增，消除重叠 ----
        overlap_fixed = 0
        for i in range(1, len(merged)):
            prev = merged[i - 1]
            cur = merged[i]
            if cur.start_time < prev.end_time:
                overlap_fixed += 1
                mid = round((prev.end_time + cur.start_time) / 2, 3)
                if mid <= prev.start_time:
                    mid = round(prev.end_time, 3)
                merged[i - 1] = TranscriptionSegment(
                    start_time=prev.start_time,
                    end_time=mid,
                    text=prev.text,
                    confidence=prev.confidence,
                    char_timestamps=getattr(prev, 'char_timestamps', []),
                )
                merged[i] = TranscriptionSegment(
                    start_time=mid,
                    end_time=max(cur.end_time, mid + 0.001),
                    text=cur.text,
                    confidence=cur.confidence,
                    char_timestamps=getattr(cur, 'char_timestamps', []),
                )

        if overlap_fixed:
            logger.info(f"修复 {overlap_fixed} 处字幕时间重叠")

        logger.info(f"从 char_timestamps 构建 {len(merged)} 个 segments")
        return merged

    def _postprocess_chunked_result(
        self,
        merged_result: dict,
        language: str,
        timestamp_mode: str,
        start_time: float,
        silence_ranges: list = None,
    ) -> TranscriptionResult:
        """对分块合并结果进行后处理并构建最终的 TranscriptionResult（sync/async 共用）"""
        # 提取逐字时间戳
        merged_char_ts = []
        if timestamp_mode in ("char", "sentence"):
            raw_ts = merged_result.get("char_timestamps", [])
            merged_char_ts = [CharTimestamp(**ts) for ts in raw_ts]
            logger.info(f"合并后逐字时间戳: {len(merged_char_ts)} 个")

        # 提取 VAD 分段
        raw_vad_segments = merged_result.get("vad_segments", [])
        vad_segments = []
        for vs in raw_vad_segments:
            vad_segments.append(TranscriptionSegment(
                start_time=vs["start_time"],
                end_time=vs["end_time"],
                text=vs["text"],
                confidence=0.95,
            ))
        logger.info(f"合并后 VAD 分段: {len(vad_segments)} 个")

        # 后处理：清理特殊标记
        raw_text = merged_result.get("text", "")
        if raw_text:
            raw_text = self._clean_special_tokens(raw_text)

        if not raw_text:
            logger.warning(
                f"转录结果为空: 原始文本长度={len(merged_result.get('text', ''))}, "
                f"音频时长={merged_result.get('end_time', 0) - merged_result.get('start_time', 0):.1f}s"
            )

        # 添加标点符号（仅用于确定断句位置）
        punctuated_text = raw_text
        if raw_text and self.enable_punctuation:
            try:
                punctuated_text = self._add_punctuation(raw_text, language)
            except Exception as e:
                logger.warning(f"标点符号处理失败: {e}")

        # 构建字幕 segments：优先使用 VAD 分段，回退到标点断句
        segments = []
        if timestamp_mode in ("char", "sentence") and merged_char_ts:
            try:
                logger.info(f"开始构建字幕 segments: raw_text 长度={len(raw_text)}, "
                           f"punctuated_text 长度={len(punctuated_text)}, "
                           f"char_ts 数量={len(merged_char_ts)}, "
                           f"VAD 分段={len(vad_segments)}")
                if vad_segments:
                    segments = self._build_segments_vad_first(
                        vad_segments, merged_char_ts, punctuated_text, raw_text,
                        silence_ranges=silence_ranges,
                    )
                else:
                    segments = self._build_segments_by_punctuation_then_align(
                        raw_text, punctuated_text, merged_char_ts
                    )
                logger.info(f"构建字幕 segments 成功: {len(segments)} 个片段")
            except Exception as e:
                logger.error(f"构建字幕 segments 失败: {e}")
                import traceback
                logger.error(traceback.format_exc())
                # 回退到简单的 segments
                segments = []

        # VAD 边界锚定：将字幕时间戳对齐到语音段边界
        if vad_segments and segments:
            try:
                from utils.subtitle_timing import anchor_segments_to_vad
                segments = anchor_segments_to_vad(segments, vad_segments)
                logger.info(f"VAD 边界锚定完成: {len(segments)} 条字幕")
            except Exception as e:
                logger.warning(f"VAD 边界锚定失败: {e}")

        # 静音区间约束：确保字幕时间戳不落入静音区间
        if silence_ranges and segments:
            try:
                from utils.subtitle_timing import enforce_silence_boundaries
                segments = enforce_silence_boundaries(segments, silence_ranges)
                logger.info(f"静音边界约束完成: {len(segments)} 条字幕")
            except Exception as e:
                logger.warning(f"静音边界约束失败: {e}")

        # 文本模式使用带标点的文本，字幕模式使用原始文本（不含标点）
        final_text = punctuated_text if timestamp_mode == "none" else raw_text

        processing_time = time.time() - start_time
        logger.info(f"分块转录完成，总耗时: {processing_time:.2f}秒")

        return TranscriptionResult(
            text=final_text.strip(),
            language=merged_result.get("language", language),
            confidence=merged_result.get("confidence", 0.95),
            segments=segments,
            char_timestamps=merged_char_ts,
            processing_time=processing_time,
            whisper_model=self.model_name,
        )

    def _extract_char_ts_from_raw_result(
        self, result, time_offset: float = 0.0
    ) -> List[dict]:
        """
        从 SenseVoice output_timestamp=True 的原始结果中提取逐字时间戳。

        Args:
            result: model.generate() 的原始返回值
            time_offset: 时间偏移量（秒），用于分块场景

        Returns:
            List[dict]: [{"word": "字", "start": 1.28, "end": 1.48}, ...]
        """
        char_ts_list = []

        try:
            if result is None or isinstance(result, (int, str)):
                return []

            if not hasattr(result, '__len__') or len(result) == 0:
                return []

            first_result = result[0]
            if isinstance(first_result, (int, float, str)):
                return []

            # 统一为列表处理
            entries = first_result if isinstance(first_result, (list, tuple)) else [first_result]

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                words = entry.get("words", [])
                timestamps = entry.get("timestamp", [])

                if not words or not timestamps:
                    continue

                # 处理长度不匹配
                if len(words) != len(timestamps):
                    logger.warning(
                        f"words({len(words)}) 与 timestamp({len(timestamps)}) 长度不匹配"
                    )
                    min_len = min(len(words), len(timestamps))
                    words = words[:min_len]
                    timestamps = timestamps[:min_len]

                for w, ts in zip(words, timestamps):
                    if not isinstance(ts, (list, tuple)) or len(ts) < 2:
                        continue
                    clean_w = self._clean_special_tokens(str(w))
                    if not clean_w or clean_w.startswith("<|") or clean_w.startswith("|>"):
                        continue
                    try:
                        start_s = float(ts[0]) / 1000.0 + time_offset
                        end_s = float(ts[1]) / 1000.0 + time_offset
                        if end_s < start_s:
                            continue
                        duration = end_s - start_s
                        max_word_duration = 2.0
                        if duration > max_word_duration:
                            end_s = start_s + min(duration, max(len(clean_w) * 0.3, 1.0))
                            logger.debug(
                                f"裁剪异常长词: '{clean_w}' {start_s:.3f}-{float(ts[1])/1000.0+time_offset:.3f}s "
                                f"(dura={duration:.2f}s) -> {start_s:.3f}-{end_s:.3f}s"
                            )
                        char_ts_list.append({
                            "word": clean_w,
                            "start": round(start_s, 3),
                            "end": round(end_s, 3)
                        })
                    except (ValueError, TypeError):
                        continue

        except Exception as e:
            logger.warning(f"提取逐字时间戳时出错: {e}")

        return char_ts_list

    def _extract_vad_segments_from_result(
        self,
        result,
        time_offset: float = 0.0,
    ) -> List[dict]:
        """
        从 SenseVoice 结果中提取 VAD 分段信息。

        SenseVoice with merge_vad=True 返回的每个 entry 对应一个人声段，
        包含准确的 start/end 时间边界。

        Returns:
            List[dict]: [{"text": "...", "start_time": ..., "end_time": ...}]
        """
        vad_segments = []

        try:
            if result is None or isinstance(result, (int, str)):
                return []

            if not hasattr(result, '__len__') or len(result) == 0:
                return []

            first_result = result[0]
            if isinstance(first_result, (int, float, str)):
                return []

            entries = first_result if isinstance(first_result, (list, tuple)) else [first_result]

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                words = entry.get("words", [])
                timestamps = entry.get("timestamp", [])
                entry_text = entry.get("text", "") or entry.get("sentence", "")
                entry_text = self._clean_special_tokens(entry_text)

                if not words or not timestamps:
                    continue

                # 从 words/timestamps 计算分段的准确起止时间
                valid_starts = []
                valid_ends = []
                for w, ts in zip(words, timestamps):
                    if not isinstance(ts, (list, tuple)) or len(ts) < 2:
                        continue
                    clean_w = self._clean_special_tokens(str(w))
                    if not clean_w or clean_w.startswith("<|") or clean_w.startswith("|>"):
                        continue
                    try:
                        start_s = float(ts[0]) / 1000.0 + time_offset
                        end_s = float(ts[1]) / 1000.0 + time_offset
                        if end_s >= start_s:
                            if (end_s - start_s) > 2.0:
                                end_s = start_s + min(len(clean_w) * 0.3, 1.0)
                            valid_starts.append(start_s)
                            valid_ends.append(end_s)
                    except (ValueError, TypeError):
                        continue

                if valid_starts and valid_ends:
                    # 优先使用 entry_text（保留空格，适合英文等多语言文本）
                    seg_text = entry_text if entry_text else ''.join(
                        self._clean_special_tokens(str(w))
                        for w in words
                        if self._clean_special_tokens(str(w))
                        and not self._clean_special_tokens(str(w)).startswith("<|")
                    )
                    vad_segments.append({
                        "text": seg_text,
                        "start_time": round(min(valid_starts), 3),
                        "end_time": round(max(valid_ends), 3),
                    })

        except Exception as e:
            logger.debug(f"提取 VAD 分段失败: {e}")

        return vad_segments

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

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()

                logger.info("SenseVoice 模型已卸载")

        if self._fa_aligner is not None:
            self._fa_aligner.unload_model()
            self._fa_aligner = None


def create_sensevoice_transcriber(
    model_name: str = "sensevoice-small",
    device: Optional[str] = None,
    model_cache_dir: Optional[str] = None,
    language: str = "auto",
    enable_punctuation: bool = True,
    clean_special_tokens: bool = True,
    enable_chunking: bool = True,
    chunk_duration_seconds: int = 300,
    chunk_overlap_seconds: int = 2,
    min_duration_for_chunking: int = 600,
    timestamp_mode: str = "none"
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
        timestamp_mode: 时间戳模式 ('none', 'sentence', 'char')

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
        min_duration_for_chunking=min_duration_for_chunking,
        timestamp_mode=timestamp_mode
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
