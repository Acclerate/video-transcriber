"""
FunASR Forced Aligner (FA)
使用 Paraformer timestamp 模型获取精确的逐字时间戳
替代 SenseVoice 的 output_timestamp 粗粒度时间戳
"""

import os
import re
import tempfile
import time
from pathlib import Path
from typing import List, Optional, Tuple

from loguru import logger

try:
    from funasr import AutoModel
    FUNASR_AVAILABLE = True
except ImportError:
    FUNASR_AVAILABLE = False
    logger.warning("funasr 未安装，FA 强制对齐不可用")

from models.schemas import CharTimestamp

_FA_MODEL_ID = "fa-zh"

_SPECIAL_TOKEN_RE = re.compile(r'<\|[A-Za-z_]+\|>')

_CHINESE_CHARS_RE = re.compile(r'[\u4e00-\u9fff]')
_ENGLISH_WORD_RE = re.compile(r'[a-zA-Z]+')


def _estimate_syllable_weight(ch: str) -> float:
    """估算字符/音节的权重，用于时间分配"""
    if _CHINESE_CHARS_RE.match(ch):
        return 1.0
    if ch.isdigit():
        return 0.8
    if ch.isascii() and ch.isalpha():
        return 0.85  # 提高英文权重，从 0.7 -> 0.85
    if ch in '-_':
        return 0.1  # 连字符权重极低
    return 0.4


def _split_into_syllable_groups(text: str) -> List[Tuple[str, float]]:
    groups: List[Tuple[str, float]] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if _CHINESE_CHARS_RE.match(ch):
            groups.append((ch, 1.0))
            i += 1
        elif ch.isascii() and ch.isalpha():
            j = i
            while j < len(text) and text[j].isascii() and text[j].isalpha():
                j += 1
            word = text[i:j]
            weight = 0.85 * len(word)
            groups.append((word, weight))
            i = j
        elif ch.isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            groups.append((text[i:j], 0.8 * (j - i)))
            i = j
        elif ch in '-_':
            groups.append((ch, 0.1))
            i += 1
        else:
            i += 1
    return groups


class ForcedAligner:
    """基于 FunASR fa-zh 强制对齐模型的强制对齐器"""

    def __init__(
        self,
        model_cache_dir: str = "./models_cache",
        device: str = "cpu",
        vad_offset_ms: float = 50.0,
        force_time_shift: float = 0.0,
    ):
        self.model_cache_dir = model_cache_dir
        self.device = device
        self.model = None
        self._loaded = False
        self._vad_offset_ms = vad_offset_ms
        self._force_time_shift = force_time_shift

    def load_model(self) -> bool:
        if not FUNASR_AVAILABLE:
            logger.warning("funasr 不可用，跳过 FA 模型加载")
            return False

        if self._loaded and self.model is not None:
            return True

        try:
            logger.info(f"正在加载 FA 模型: {_FA_MODEL_ID}")
            os.environ['MODELSCOPE_CACHE'] = self.model_cache_dir
            Path(self.model_cache_dir).mkdir(parents=True, exist_ok=True)

            start = time.time()
            self.model = AutoModel(
                model=_FA_MODEL_ID,
                device="cpu",
                cache_dir=self.model_cache_dir,
                disable_pbar=False,
                disable_log=False,
            )

            import torch
            if self.device == "cuda" and torch.cuda.is_available():
                for comp_name in ['model', 'vad_model', 'punc_model', 'frontend']:
                    if hasattr(self.model, comp_name):
                        comp = getattr(self.model, comp_name)
                        if comp is not None and hasattr(comp, 'to'):
                            try:
                                comp.to("cuda")
                            except Exception:
                                pass

            self._loaded = True
            elapsed = time.time() - start
            logger.info(f"FA 模型加载完成 (耗时 {elapsed:.2f}s)")
            return True

        except Exception as e:
            logger.warning(f"FA 模型加载失败: {e}，将回退到 SenseVoice 时间戳")
            self.model = None
            self._loaded = False
            return False

    def unload_model(self):
        if self.model is not None:
            del self.model
            self.model = None
            self._loaded = False
            try:
                import torch
                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
            logger.info("FA 模型已卸载")

    def align(
        self,
        audio_path: str,
        text: str,
        time_offset: float = 0.0,
    ) -> Tuple[Optional[str], List[CharTimestamp]]:
        """
        对音频和已知文本进行强制对齐，获取逐字时间戳

        Args:
            audio_path: 音频文件路径
            text: 已识别文本，用于强制对齐
            time_offset: 时间偏移量（秒），用于分块场景

        Returns:
            (aligned_text, char_timestamps) 元组
        """
        if not self._loaded or self.model is None:
            return None, []

        clean_text = self._clean_alignment_text(text)
        if not clean_text:
            return None, []

        text_file = None
        try:
            logger.info(f"FA 强制对齐: {audio_path}")
            text_file = self._write_alignment_text(clean_text)
            result = self.model.generate(
                input=(audio_path, text_file),
                data_type=("sound", "text"),
                vad_offset=self._vad_offset_ms / 1000.0,
            )

            if not result or len(result) == 0:
                logger.warning("FA 模型返回空结果")
                return None, []

            return self._parse_fa_result(result[0], time_offset)

        except Exception as e:
            logger.warning(f"FA 强制对齐失败: {e}")
            return None, []
        finally:
            if text_file:
                try:
                    os.remove(text_file)
                except OSError:
                    pass

    @staticmethod
    def _clean_alignment_text(text: str) -> str:
        text = _SPECIAL_TOKEN_RE.sub('', text)
        return ''.join(ch for ch in text if ch.strip())

    @staticmethod
    def _write_alignment_text(text: str) -> str:
        with tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".txt",
            encoding="utf-8",
            delete=False,
        ) as f:
            f.write(text)
            return f.name

    def _parse_fa_result(
        self,
        first_result,
        time_offset: float = 0.0,
    ) -> Tuple[Optional[str], List[CharTimestamp]]:
        if isinstance(first_result, dict):
            return self._parse_dict_result(first_result, time_offset)
        if isinstance(first_result, (list, tuple)) and len(first_result) > 0:
            if isinstance(first_result[0], dict):
                combined_text = ""
                combined_ts: List[CharTimestamp] = []
                for entry in first_result:
                    text, ts = self._parse_dict_result(entry, time_offset)
                    if text:
                        combined_text += text
                    combined_ts.extend(ts)
                return combined_text, combined_ts
        return None, []

    @staticmethod
    def _timestamp_to_seconds(ts_pair, time_offset: float, force_time_shift: float = 0.0) -> Optional[Tuple[float, float]]:
        if not isinstance(ts_pair, (list, tuple)) or len(ts_pair) < 2:
            return None
        try:
            start_s = float(ts_pair[0]) / 1000.0 + time_offset + force_time_shift
            end_s = float(ts_pair[1]) / 1000.0 + time_offset + force_time_shift
        except (ValueError, TypeError):
            return None
        if end_s < start_s:
            return None
        return start_s, end_s

    @staticmethod
    def _timestamp_token(token: str, start_s: float, end_s: float) -> CharTimestamp:
        return CharTimestamp(
            word=token,
            start=round(start_s, 3),
            end=round(end_s, 3),
        )

    def _parse_dict_result(
        self,
        entry: dict,
        time_offset: float = 0.0,
    ) -> Tuple[Optional[str], List[CharTimestamp]]:
        text = entry.get("text", "") or entry.get("sentence", "")
        if isinstance(text, str):
            text = _SPECIAL_TOKEN_RE.sub('', text).strip()

        timestamps = entry.get("timestamp", [])
        if not timestamps or not text:
            return text, []

        if timestamps:
            raw_first = timestamps[0] if isinstance(timestamps[0], (list, tuple)) else (0, 0)
            raw_last = timestamps[-1] if isinstance(timestamps[-1], (list, tuple)) else (0, 0)
            logger.debug(f"FA raw: text_len={len(text)}, timestamps={len(timestamps)}, first={raw_first}, last={raw_last}")

        spaced_tokens = [token for token in text.split() if token]
        if len(spaced_tokens) == len(timestamps):
            token_timestamps: List[CharTimestamp] = []
            for token, ts_pair in zip(spaced_tokens, timestamps):
                seconds = self._timestamp_to_seconds(ts_pair, time_offset, self._force_time_shift)
                if seconds is None:
                    continue
                token_timestamps.append(self._timestamp_token(token, *seconds))
            expanded = expand_char_timestamps_syllable_aware(token_timestamps)
            combined_text = ''.join(spaced_tokens)
            logger.debug(f"FA token expand: {len(timestamps)} tokens -> {len(expanded)} chars")
            return combined_text, expanded

        compact_text = ''.join(ch for ch in text if ch.strip())
        char_timestamps: List[CharTimestamp] = []
        char_idx = 0

        for ts_pair in timestamps:
            if char_idx >= len(compact_text):
                break

            seconds = self._timestamp_to_seconds(ts_pair, time_offset, self._force_time_shift)
            if seconds is None:
                continue

            char_timestamps.append(self._timestamp_token(compact_text[char_idx], *seconds))
            char_idx += 1

        return compact_text, char_timestamps


def distribute_timestamps_by_syllable(
    word_ts: CharTimestamp,
) -> List[CharTimestamp]:
    """
    基于音节/分词的时间分配，替换简单的均分策略

    对于多字符 token（如 "chatmemoryprovider"）：
    1. 按语言特征分组（中文=1字1组，英文=1词1组）
    2. 每组按音节权重分配时长
    3. 重读音节获得更长的时间窗口
    """
    text = word_ts.word.strip()
    if not text:
        return []
    if len(text) == 1 or word_ts.end <= word_ts.start:
        return [word_ts]

    duration = word_ts.end - word_ts.start
    groups = _split_into_syllable_groups(text)

    if not groups:
        char_duration = duration / len(text)
        return [
            CharTimestamp(
                word=ch,
                start=round(word_ts.start + char_duration * i, 3),
                end=round(word_ts.start + char_duration * (i + 1), 3),
            )
            for i, ch in enumerate(text)
        ]

    total_weight = sum(w for _, w in groups)
    if total_weight <= 0:
        total_weight = 1.0

    result: List[CharTimestamp] = []
    current_time = word_ts.start

    for group_text, weight in groups:
        group_duration = duration * (weight / total_weight)
        n_chars = len(group_text)
        char_dur = group_duration / n_chars if n_chars > 0 else group_duration

        for i, ch in enumerate(group_text):
            start = current_time + char_dur * i
            end = current_time + char_dur * (i + 1)
            result.append(CharTimestamp(
                word=ch,
                start=round(start, 3),
                end=round(end, 3),
            ))
        current_time += group_duration

    return result


def expand_char_timestamps_syllable_aware(
    char_timestamps: List[CharTimestamp],
) -> List[CharTimestamp]:
    """
    使用音节感知的时间展开替代均分展开

    对每个 CharTimestamp：
    - 单字符 → 保留原样
    - 多字符 → 使用 distribute_timestamps_by_syllable 展开
    """
    expanded: List[CharTimestamp] = []
    for ts in char_timestamps:
        text = ts.word.strip()
        if not text:
            continue
        if len(text) == 1 or ts.end <= ts.start:
            expanded.append(ts)
            continue
        expanded.extend(distribute_timestamps_by_syllable(ts))
    return expanded
