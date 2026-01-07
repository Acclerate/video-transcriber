"""
通用辅助函数
"""

import re
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from urllib.parse import urlparse, parse_qs

from loguru import logger


def validate_url(url: str) -> bool:
    """
    验证URL格式是否正确

    Args:
        url: 待验证的URL

    Returns:
        bool: 是否为有效URL
    """
    try:
        if not url or not isinstance(url, str):
            return False

        # 补全协议
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        parsed = urlparse(url)
        return bool(parsed.netloc and parsed.scheme in ['http', 'https'])
    except Exception:
        return False


def extract_domain(url: str) -> Optional[str]:
    """
    从URL中提取域名

    Args:
        url: URL地址

    Returns:
        Optional[str]: 域名
    """
    try:
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        parsed = urlparse(url)
        domain = parsed.netloc.lower()

        # 移除www前缀
        if domain.startswith('www.'):
            domain = domain[4:]

        return domain
    except Exception:
        return None


def parse_query_params(url: str) -> Dict[str, List[str]]:
    """
    解析URL查询参数

    Args:
        url: URL地址

    Returns:
        Dict[str, List[str]]: 查询参数字典
    """
    try:
        parsed = urlparse(url)
        return parse_qs(parsed.query)
    except Exception:
        return {}


def truncate_text(text: str, max_length: int = 100, suffix: str = "...") -> str:
    """
    截断文本并添加省略号

    Args:
        text: 原始文本
        max_length: 最大长度
        suffix: 省略号后缀

    Returns:
        str: 截断后的文本
    """
    if len(text) <= max_length:
        return text

    return text[:max_length - len(suffix)] + suffix


def extract_numbers(text: str) -> List[float]:
    """
    从文本中提取数字

    Args:
        text: 文本内容

    Returns:
        List[float]: 数字列表
    """
    try:
        pattern = r'-?\d+\.?\d*'
        matches = re.findall(pattern, text)
        return [float(match) for match in matches if match]
    except Exception:
        return []


def normalize_text(text: str) -> str:
    """
    标准化文本（去除多余空格、标点符号等）

    Args:
        text: 原始文本

    Returns:
        str: 标准化后的文本
    """
    # 去除多余空格
    text = re.sub(r'\s+', ' ', text)

    # 去除首尾空格
    text = text.strip()

    # 标准化换行符
    text = text.replace('\r\n', '\n').replace('\r', '\n')

    return text


def time_ago(dt: datetime) -> str:
    """
    计算相对时间描述

    Args:
        dt: 时间对象

    Returns:
        str: 相对时间描述
    """
    now = datetime.now()
    diff = now - dt

    seconds = diff.total_seconds()

    if seconds < 60:
        return "刚刚"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes}分钟前"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours}小时前"
    elif seconds < 2592000:  # 30天
        days = int(seconds // 86400)
        return f"{days}天前"
    else:
        return dt.strftime("%Y-%m-%d")


def retry_on_exception(
    max_retries: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,)
):
    """
    重试装饰器

    Args:
        max_retries: 最大重试次数
        delay: 初始延迟时间
        backoff: 延迟倍数
        exceptions: 需要重试的异常类型
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(f"重试{max_retries}次后仍然失败: {e}")
                        raise

                    logger.warning(f"第{attempt + 1}次尝试失败，{current_delay}秒后重试: {e}")
                    await asyncio.sleep(current_delay)
                    current_delay *= backoff

        def sync_wrapper(*args, **kwargs):
            import time
            current_delay = delay

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_retries:
                        logger.error(f"重试{max_retries}次后仍然失败: {e}")
                        raise

                    logger.warning(f"第{attempt + 1}次尝试失败，{current_delay}秒后重试: {e}")
                    time.sleep(current_delay)
                    current_delay *= backoff

        # 判断是否为异步函数
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper

    return decorator


class RateLimiter:
    """简单的速率限制器"""

    def __init__(self, max_calls: int, time_window: float):
        """
        初始化速率限制器

        Args:
            max_calls: 时间窗口内最大调用次数
            time_window: 时间窗口长度（秒）
        """
        self.max_calls = max_calls
        self.time_window = time_window
        self.calls = []

    async def acquire(self) -> bool:
        """
        获取调用许可

        Returns:
            bool: 是否允许调用
        """
        now = asyncio.get_event_loop().time()

        # 清理过期记录
        self.calls = [call_time for call_time in self.calls
                     if now - call_time < self.time_window]

        # 检查是否超过限制
        if len(self.calls) >= self.max_calls:
            return False

        # 记录本次调用
        self.calls.append(now)
        return True

    async def wait_for_slot(self):
        """等待可用的调用槽位"""
        while not await self.acquire():
            await asyncio.sleep(0.1)


def batch_items(items: List[Any], batch_size: int) -> List[List[Any]]:
    """
    将列表分批处理

    Args:
        items: 原始列表
        batch_size: 批次大小

    Returns:
        List[List[Any]]: 分批后的列表
    """
    batches = []
    for i in range(0, len(items), batch_size):
        batches.append(items[i:i + batch_size])
    return batches
