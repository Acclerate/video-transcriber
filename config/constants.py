"""
常量定义
应用中使用的各种常量
"""

from typing import Dict, List

# ============================================================
# Whisper 模型信息
# ============================================================

WHISPER_MODELS: Dict[str, Dict[str, str]] = {
    "tiny": {
        "size": "39MB",
        "speed": "10x",
        "accuracy": "★★☆☆☆",
        "description": "最快速度，适合快速预览",
    },
    "base": {
        "size": "74MB",
        "speed": "7x",
        "accuracy": "★★★☆☆",
        "description": "平衡速度和准确率，适合日常使用",
    },
    "small": {
        "size": "244MB",
        "speed": "4x",
        "accuracy": "★★★★☆",
        "description": "推荐使用，准确率高",
    },
    "medium": {
        "size": "769MB",
        "speed": "2x",
        "accuracy": "★★★★★",
        "description": "高准确率，适合重要内容",
    },
    "large": {
        "size": "1550MB",
        "speed": "1x",
        "accuracy": "★★★★★",
        "description": "最高准确率，适合专业用途",
    },
}

WHISPER_MODEL_NAMES = list(WHISPER_MODELS.keys())

# ============================================================
# 支持的语言
# ============================================================

SUPPORTED_LANGUAGES: Dict[str, str] = {
    "auto": "自动检测",
    "zh": "中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "es": "西班牙语",
    "fr": "法语",
    "de": "德语",
    "ru": "俄语",
    "it": "意大利语",
    "pt": "葡萄牙语",
    "nl": "荷兰语",
    "sv": "瑞典语",
    "no": "挪威语",
    "da": "丹麦语",
    "fi": "芬兰语",
    "pl": "波兰语",
    "tr": "土耳其语",
    "ar": "阿拉伯语",
    "hi": "印地语",
    "th": "泰语",
    "vi": "越南语",
}

LANGUAGE_CODES = list(SUPPORTED_LANGUAGES.keys())

# ============================================================
# 输出格式
# ============================================================

OUTPUT_FORMATS = {
    "txt": "纯文本",
    "json": "JSON 格式",
    "srt": "SRT 字幕",
    "vtt": "VTT 字幕",
}

OUTPUT_FORMAT_EXTENSIONS = list(OUTPUT_FORMATS.keys())

# ============================================================
# 文件大小限制
# ============================================================

MIN_FILE_SIZE_BYTES = 1024  # 最小文件大小 1KB
CHUNK_SIZE = 8192  # 读取文件块大小

# ============================================================
# 超时和间隔设置
# ============================================================

DEFAULT_TIMEOUT = 300  # 默认超时 5 分钟
CLEANUP_INTERVAL = 3600  # 清理间隔 1 小时
TASK_CHECK_INTERVAL = 10  # 任务检查间隔 10 秒

# ============================================================
# 音频处理常量
# ============================================================

# Whisper 推荐的音频参数
WHISPER_SAMPLE_RATE = 16000  # 16kHz
WHISPER_CHANNELS = 1  # 单声道

# 音频质量参数
DEFAULT_SAMPLE_RATE = 44100  # 44.1kHz (MP3 导出)
DEFAULT_BITRATE = "192k"  # MP3 比特率
TARGET_DBFS = -20.0  # 目标音量

# 静音检测参数
SILENCE_THRESHOLD = -40  # 静音阈值 (dB)
MIN_SILENCE_LEN = 1000  # 最小静音长度 (ms)
KEEP_SILENCE = 500  # 保留静音 (ms)

# ============================================================
# 任务状态
# ============================================================

class TaskStatus:
    """任务状态常量"""
    PENDING = "pending"
    EXTRACTING = "extracting"
    TRANSCRIBING = "transcribing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

TASK_STATUS_CHOICES = [
    TaskStatus.PENDING,
    TaskStatus.EXTRACTING,
    TaskStatus.TRANSCRIBING,
    TaskStatus.COMPLETED,
    TaskStatus.FAILED,
    TaskStatus.CANCELLED,
]

# ============================================================
# 错误消息
# ============================================================

ERROR_MESSAGES = {
    "file_not_found": "文件不存在",
    "file_too_large": "文件大小超过限制",
    "unsupported_format": "不支持的文件格式",
    "ffmpeg_not_found": "FFmpeg 未安装或不可用",
    "model_not_loaded": "Whisper 模型未加载",
    "transcription_failed": "转录失败",
    "audio_extraction_failed": "音频提取失败",
}

# ============================================================
# HTTP 状态码
# ============================================================

class HTTPStatus:
    """HTTP 状态码常量"""
    OK = 200
    CREATED = 201
    BAD_REQUEST = 400
    UNAUTHORIZED = 401
    FORBIDDEN = 403
    NOT_FOUND = 404
    UNPROCESSABLE_ENTITY = 422
    TOO_MANY_REQUESTS = 429
    INTERNAL_SERVER_ERROR = 500
    SERVICE_UNAVAILABLE = 503

# ============================================================
# API 响应消息
# ============================================================

API_MESSAGES = {
    "task_created": "任务创建成功",
    "task_processing": "任务处理中",
    "task_completed": "任务完成",
    "task_failed": "任务失败",
    "invalid_request": "无效的请求",
    "missing_parameter": "缺少必需参数",
    "invalid_file": "无效的文件",
    "rate_limit_exceeded": "请求过于频繁，请稍后再试",
}

# ============================================================
# 时间格式
# ============================================================

DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DATE_FORMAT = "%Y-%m-%d"
TIME_FORMAT = "%H:%M:%S"

# 文件名时间格式
FILENAME_DATETIME_FORMAT = "%Y%m%d_%H%M%S"

# ============================================================
# 正则表达式模式
# ============================================================

# 文件名清理正则
INVALID_FILENAME_CHARS = r'[<>:"/\\|?*]'

# ============================================================
# 进度权重
# ============================================================

# 转录任务各阶段权重
PROGRESS_WEIGHTS = {
    "validation": 0.05,      # 5% 文件验证
    "extraction": 0.40,      # 40% 音频提取
    "transcription": 0.50,   # 50% 转录
    "processing": 0.05,      # 5% 结果处理
}

# ============================================================
# 默认值
# ============================================================

DEFAULT_CONCURRENT_TASKS = 3
DEFAULT_BATCH_SIZE = 100
DEFAULT_PAGE_SIZE = 20
MAX_RETRY_ATTEMPTS = 3
RETRY_DELAY = 1.0  # seconds
RETRY_BACKOFF = 2.0  # multiplier
