"""
重试机制模块
提供带指数退避的重试装饰器
"""

import asyncio
import functools
import random
from typing import Callable, Optional, Type, Tuple, Any
from loguru import logger


class RetryConfig:
    """重试配置"""

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
        jitter: bool = True
    ):
        """
        初始化重试配置

        Args:
            max_attempts: 最大重试次数
            base_delay: 基础延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            exponential_base: 指数退避基数
            jitter: 是否添加随机抖动
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """
        计算第N次重试的延迟时间

        Args:
            attempt: 重试次数（从1开始）

        Returns:
            float: 延迟时间（秒）
        """
        # 指数退避
        delay = min(
            self.base_delay * (self.exponential_base ** (attempt - 1)),
            self.max_delay
        )

        # 添加随机抖动避免惊群效应
        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)

        return delay


class RetryError(Exception):
    """重试失败异常"""

    def __init__(
        self,
        message: str,
        attempts: int,
        last_exception: Optional[Exception] = None
    ):
        """
        初始化重试异常

        Args:
            message: 错误消息
            attempts: 尝试次数
            last_exception: 最后一次异常
        """
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(message)


def retry_on_exception(
    max_attempts: int = 3,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    on_retry: Optional[Callable[[int, Exception], None]] = None
):
    """
    同步函数重试装饰器

    Args:
        max_attempts: 最大重试次数
        exceptions: 需要重试的异常类型
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        exponential_base: 指数退避基数
        on_retry: 重试时的回调函数

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            config = RetryConfig(
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                exponential_base=exponential_base
            )

            last_exception = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt >= config.max_attempts:
                        logger.error(
                            f"{func.__name__} 重试失败: 已尝试 {config.max_attempts} 次"
                        )
                        raise RetryError(
                            f"{func.__name__} 在 {config.max_attempts} 次尝试后仍然失败",
                            attempts=config.max_attempts,
                            last_exception=e
                        ) from e

                    delay = config.get_delay(attempt)
                    logger.warning(
                        f"{func.__name__} 失败 (第 {attempt} 次): {e}, "
                        f"{delay:.1f} 秒后重试..."
                    )

                    if on_retry:
                        on_retry(attempt, e)

                    import time
                    time.sleep(delay)

        return wrapper

    return decorator


def async_retry_on_exception(
    max_attempts: int = 3,
    exceptions: Tuple[Type[Exception], ...] = (Exception,),
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    on_retry: Optional[Callable[[int, Exception], None]] = None
):
    """
    异步函数重试装饰器

    Args:
        max_attempts: 最大重试次数
        exceptions: 需要重试的异常类型
        base_delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        exponential_base: 指数退避基数
        on_retry: 重试时的回调函数

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            config = RetryConfig(
                max_attempts=max_attempts,
                base_delay=base_delay,
                max_delay=max_delay,
                exponential_base=exponential_base
            )

            last_exception = None

            for attempt in range(1, config.max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exception = e

                    if attempt >= config.max_attempts:
                        logger.error(
                            f"{func.__name__} 重试失败: 已尝试 {config.max_attempts} 次"
                        )
                        raise RetryError(
                            f"{func.__name__} 在 {config.max_attempts} 次尝试后仍然失败",
                            attempts=config.max_attempts,
                            last_exception=e
                        ) from e

                    delay = config.get_delay(attempt)
                    logger.warning(
                        f"{func.__name__} 失败 (第 {attempt} 次): {e}, "
                        f"{delay:.1f} 秒后重试..."
                    )

                    if on_retry:
                        on_retry(attempt, e)

                    await asyncio.sleep(delay)

        return wrapper

    return decorator


# 预定义的重试配置

# 网络请求重试 - 短延迟，快速重试
NETWORK_RETRY = RetryConfig(
    max_attempts=3,
    base_delay=0.5,
    max_delay=5.0,
    exponential_base=2.0
)

# Whisper 模型重试 - 中等延迟
WHISPER_RETRY = RetryConfig(
    max_attempts=2,
    base_delay=2.0,
    max_delay=10.0,
    exponential_base=2.0
)

# 文件操作重试 - 长延迟
FILE_OPERATION_RETRY = RetryConfig(
    max_attempts=3,
    base_delay=1.0,
    max_delay=30.0,
    exponential_base=2.0
)
