"""
应用配置管理
使用 pydantic-settings 进行配置管理
"""

import os
from pathlib import Path
from typing import Optional, List
from pydantic import field_validator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    应用配置类
    从环境变量和 .env 文件加载配置
    """

    # ============================================================
    # 应用基础配置
    # ============================================================
    APP_NAME: str = "Video Transcriber"
    APP_VERSION: str = "2.0.0"
    DEBUG: bool = False
    ENVIRONMENT: str = "production"  # development, staging, production

    # ============================================================
    # 服务配置
    # ============================================================
    HOST: str = "0.0.0.0"
    PORT: int = 8665
    WORKERS: int = 1

    # ============================================================
    # API 配置
    # ============================================================
    API_V1_PREFIX: str = "/api/v1"
    DOCS_URL: str = "/docs"
    REDOC_URL: str = "/redoc"
    OPENAPI_URL: str = "/openapi.json"

    # CORS 配置
    CORS_ORIGINS: List[str] = ["*"]
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # 速率限制
    RATE_LIMIT_PER_MINUTE: int = 60
    RATE_LIMIT_PER_HOUR: int = 1000

    # ============================================================
    # SenseVoice 语音识别配置
    # ============================================================
    DEFAULT_MODEL: str = "sensevoice-small"  # 使用 SenseVoice Small (多语言，中文优化)
    ENABLE_GPU: bool = True
    # 模型缓存目录 - 默认使用 D 盘，避免占用 C 盘空间
    MODEL_CACHE_DIR: str = "D:/models_cache/sensevoice"

    # 转录配置
    # 默认使用中文以获得最佳识别效果
    # 如需自动检测，可设置为 "auto"
    DEFAULT_LANGUAGE: str = "zh"
    DEFAULT_TEMPERATURE: float = 0.0
    ENABLE_WORD_TIMESTAMPS: bool = False

    # 文本后处理配置
    # 是否添加标点符号（使用FunASR的punctuation模型）
    ENABLE_PUNCTUATION: bool = True
    # 是否清理SenseVoice输出的特殊标记（如 <|zh|><|NEUTRAL|> 等）
    CLEAN_SPECIAL_TOKENS: bool = True

    # 音频分块处理配置
    # 启用预先分割，避免 OOM
    ENABLE_AUDIO_CHUNKING: bool = True
    CHUNK_DURATION_SECONDS: int = 300  # 每块5分钟（秒）- 适配8GB显存和内存
    CHUNK_OVERLAP_SECONDS: int = 1  # 块之间重叠时间（秒）
    MIN_DURATION_FOR_CHUNKING: int = 600  # 超过10分钟的音频才启用分块处理

    # 语言验证：确保语言代码有效
    SUPPORTED_LANGUAGES: List[str] = [
        "zh",  # 中文
        "en",  # 英语
        "ja",  # 日语
        "ko",  # 韩语
        "es",  # 西班牙语
        "fr",  # 法语
        "de",  # 德语
        "ru",  # 俄语
        "auto" # 自动检测
    ]

    # ============================================================
    # 文件配置
    # ============================================================
    TEMP_DIR: str = "./temp"
    OUTPUT_DIR: str = "./output"
    MAX_FILE_SIZE: int = 1024  # MB (1GB)
    CLEANUP_AFTER: int = 3600  # seconds

    # 支持的格式
    VIDEO_FORMATS: List[str] = [
        ".mp4", ".avi", ".mkv", ".mov",
        ".wmv", ".flv", ".webm", ".m4v"
    ]
    AUDIO_FORMATS: List[str] = [
        ".mp3", ".wav", ".m4a", ".aac",
        ".flac", ".ogg", ".wma"
    ]

    # ============================================================
    # 音频处理配置
    # ============================================================
    AUDIO_SAMPLE_RATE: int = 16000  # 16kHz (语音识别标准采样率)
    AUDIO_CHANNELS: int = 1  # 单声道
    AUDIO_BITRATE: str = "192k"
    TARGET_DBFS: float = -20.0  # 音量标准化目标

    # 静音检测
    SILENCE_THRESHOLD: int = -40  # dB
    MIN_SILENCE_LENGTH: int = 1000  # ms
    KEEP_SILENCE: int = 500  # ms

    # ============================================================
    # 日志配置
    # ============================================================
    LOG_LEVEL: str = "INFO"
    LOG_DIR: str = "./logs"
    LOG_FILE: str = "app.log"
    LOG_TO_CONSOLE: bool = True
    LOG_ROTATION: str = "100 MB"
    LOG_RETENTION: str = "30 days"

    # ============================================================
    # 任务配置
    # ============================================================
    MAX_CONCURRENT_TASKS: int = 3
    TASK_TIMEOUT: int = 3600  # seconds
    TASK_CLEANUP_INTERVAL: int = 3600  # seconds
    TASK_RETENTION_HOURS: int = 24

    # ============================================================
    # 安全配置
    # ============================================================
    SECRET_KEY: str = "your-secret-key-change-in-production"
    ALLOWED_HOSTS: List[str] = ["*"]

    # ============================================================
    # 数据库配置 (预留)
    # ============================================================
    DATABASE_URL: Optional[str] = None
    REDIS_URL: Optional[str] = None

    # ============================================================
    # 第三方服务配置
    # ============================================================
    # 抖音/Bilibili 等平台配置
    ENABLE_PLATFORM_DOWNLOAD: bool = False
    DOWNLOAD_TIMEOUT: int = 300  # seconds
    DOWNLOAD_USER_AGENT: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    # Cookies 文件路径
    COOKIES_FILE: str = "./cookies.txt"

    # ============================================================
    # Model configuration
    # ============================================================
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    # ============================================================
    # Validators
    # ============================================================
    @field_validator("ENVIRONMENT")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """验证环境变量"""
        valid_environments = ["development", "staging", "production"]
        if v not in valid_environments:
            raise ValueError(f"ENVIRONMENT must be one of {valid_environments}")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """验证日志级别"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v_upper

    @field_validator("DEFAULT_MODEL")
    @classmethod
    def validate_model(cls, v: str) -> str:
        """验证语音识别模型"""
        valid_models = ["sensevoice-small"]
        if v not in valid_models:
            raise ValueError(f"DEFAULT_MODEL must be one of {valid_models}")
        return v

    @field_validator("DEFAULT_LANGUAGE")
    @classmethod
    def validate_language(cls, v: str) -> str:
        """验证转录语言"""
        valid_languages = ["zh", "en", "ja", "ko", "es", "fr", "de", "ru", "auto"]
        if v not in valid_languages:
            raise ValueError(
                f"DEFAULT_LANGUAGE must be one of {valid_languages}. "
                f"常见值: zh(中文), en(英语), ja(日语), auto(自动检测)"
            )
        return v

    @field_validator("PORT")
    @classmethod
    def validate_port(cls, v: int) -> int:
        """验证端口号"""
        if not 1 <= v <= 65535:
            raise ValueError("PORT must be between 1 and 65535")
        return v

    @field_validator("MAX_FILE_SIZE")
    @classmethod
    def validate_file_size(cls, v: int) -> int:
        """验证文件大小限制"""
        if v <= 0 or v > 5000:  # 最大 5GB
            raise ValueError("MAX_FILE_SIZE must be between 1 and 5000 MB")
        return v

    # ============================================================
    # Properties
    # ============================================================
    @property
    def is_development(self) -> bool:
        """是否为开发环境"""
        return self.ENVIRONMENT == "development"

    @property
    def is_production(self) -> bool:
        """是否为生产环境"""
        return self.ENVIRONMENT == "production"

    @property
    def temp_path(self) -> Path:
        """临时目录路径"""
        path = Path(self.TEMP_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def output_path(self) -> Path:
        """输出目录路径"""
        path = Path(self.OUTPUT_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def log_path(self) -> Path:
        """日志目录路径"""
        path = Path(self.LOG_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def log_file_path(self) -> Path:
        """日志文件路径"""
        return self.log_path / self.LOG_FILE

    @property
    def model_cache_path(self) -> Path:
        """模型缓存目录路径"""
        path = Path(self.MODEL_CACHE_DIR)
        path.mkdir(parents=True, exist_ok=True)
        return path

    # ============================================================
    # Class methods
    # ============================================================
    @classmethod
    def from_env(cls, env_file: str = ".env") -> "Settings":
        """从环境文件加载配置"""
        return cls(_env_file=env_file)

    def get_model_info(self, model_name: str) -> dict:
        """获取模型信息"""
        model_info = {
            "tiny": {"size": "39MB", "speed": "10x", "accuracy": "★★☆☆☆"},
            "base": {"size": "74MB", "speed": "7x", "accuracy": "★★★☆☆"},
            "small": {"size": "244MB", "speed": "4x", "accuracy": "★★★★☆"},
            "medium": {"size": "769MB", "speed": "2x", "accuracy": "★★★★★"},
            "large": {"size": "1550MB", "speed": "1x", "accuracy": "★★★★★"},
        }
        return model_info.get(model_name, {})


# 全局配置实例
settings = Settings()


def get_settings() -> Settings:
    """获取配置实例 (用于依赖注入)"""
    return settings


def reload_settings() -> Settings:
    """重新加载配置"""
    global settings
    settings = Settings()
    return settings
