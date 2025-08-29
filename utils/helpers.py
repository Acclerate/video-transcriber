"""
辅助工具函数
提供各种通用的辅助功能
"""

import os
import re
import asyncio
import hashlib
import mimetypes
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Union
from urllib.parse import urlparse, parse_qs

import aiofiles
from loguru import logger


def format_duration(seconds: float) -> str:
    """
    格式化时长为易读格式
    
    Args:
        seconds: 秒数
        
    Returns:
        str: 格式化的时长字符串
    """
    if seconds < 60:
        return f"{seconds:.1f}秒"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}分{secs}秒"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}小时{minutes}分{secs}秒"


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小为易读格式
    
    Args:
        size_bytes: 字节数
        
    Returns:
        str: 格式化的文件大小字符串
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    
    while size_bytes >= 1024.0 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    
    return f"{size_bytes:.1f} {size_names[i]}"


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


def clean_filename(filename: str, max_length: int = 255) -> str:
    """
    清理文件名，移除非法字符
    
    Args:
        filename: 原始文件名
        max_length: 最大长度
        
    Returns:
        str: 清理后的文件名
    """
    # 移除非法字符
    illegal_chars = r'<>:"/\\|?*'
    for char in illegal_chars:
        filename = filename.replace(char, '_')
    
    # 移除连续的空格和下划线
    filename = re.sub(r'\s+', ' ', filename)
    filename = re.sub(r'_+', '_', filename)
    
    # 去除首尾空格和点号
    filename = filename.strip(' .')
    
    # 限制长度
    if len(filename) > max_length:
        name, ext = os.path.splitext(filename)
        max_name_length = max_length - len(ext)
        filename = name[:max_name_length] + ext
    
    return filename or "untitled"


def get_file_hash(file_path: str, algorithm: str = "md5") -> Optional[str]:
    """
    计算文件哈希值
    
    Args:
        file_path: 文件路径
        algorithm: 哈希算法 (md5, sha1, sha256)
        
    Returns:
        Optional[str]: 哈希值
    """
    try:
        if not os.path.exists(file_path):
            return None
        
        hash_obj = hashlib.new(algorithm)
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b""):
                hash_obj.update(chunk)
        
        return hash_obj.hexdigest()
    except Exception as e:
        logger.error(f"计算文件哈希失败: {e}")
        return None


async def async_get_file_hash(file_path: str, algorithm: str = "md5") -> Optional[str]:
    """
    异步计算文件哈希值
    
    Args:
        file_path: 文件路径
        algorithm: 哈希算法
        
    Returns:
        Optional[str]: 哈希值
    """
    try:
        if not os.path.exists(file_path):
            return None
        
        hash_obj = hashlib.new(algorithm)
        
        async with aiofiles.open(file_path, 'rb') as f:
            async for chunk in f:
                hash_obj.update(chunk)
        
        return hash_obj.hexdigest()
    except Exception as e:
        logger.error(f"异步计算文件哈希失败: {e}")
        return None


def get_mime_type(file_path: str) -> Optional[str]:
    """
    获取文件MIME类型
    
    Args:
        file_path: 文件路径
        
    Returns:
        Optional[str]: MIME类型
    """
    try:
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type
    except Exception:
        return None


def is_audio_file(file_path: str) -> bool:
    """
    判断是否为音频文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 是否为音频文件
    """
    audio_extensions = {'.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg', '.wma'}
    return Path(file_path).suffix.lower() in audio_extensions


def is_video_file(file_path: str) -> bool:
    """
    判断是否为视频文件
    
    Args:
        file_path: 文件路径
        
    Returns:
        bool: 是否为视频文件
    """
    video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm', '.m4v'}
    return Path(file_path).suffix.lower() in video_extensions


def ensure_directory(directory: str) -> Path:
    """
    确保目录存在，不存在则创建
    
    Args:
        directory: 目录路径
        
    Returns:
        Path: 目录路径对象
    """
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)
    return dir_path


def get_temp_filename(prefix: str = "", suffix: str = "", extension: str = "") -> str:
    """
    生成临时文件名
    
    Args:
        prefix: 前缀
        suffix: 后缀
        extension: 扩展名
        
    Returns:
        str: 临时文件名
    """
    import uuid
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    random_id = uuid.uuid4().hex[:8]
    
    filename = f"{prefix}{timestamp}_{random_id}{suffix}"
    
    if extension and not extension.startswith('.'):
        extension = '.' + extension
    
    return filename + extension


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


if __name__ == "__main__":
    # 测试工具函数
    
    # 测试时长格式化
    print(f"30秒: {format_duration(30)}")
    print(f"90秒: {format_duration(90)}")
    print(f"3665秒: {format_duration(3665)}")
    
    # 测试文件大小格式化
    print(f"1024字节: {format_file_size(1024)}")
    print(f"1048576字节: {format_file_size(1048576)}")
    
    # 测试URL验证
    print(f"有效URL: {validate_url('https://www.example.com')}")
    print(f"无效URL: {validate_url('not-a-url')}")
    
    # 测试域名提取
    print(f"域名: {extract_domain('https://www.example.com/path')}")
    
    # 测试文件名清理
    print(f"清理文件名: {clean_filename('test<>file:name.txt')}")
    
    # 测试文本截断
    print(f"截断文本: {truncate_text('这是一个很长的文本内容', 10)}")
    
    # 测试相对时间
    past_time = datetime.now() - timedelta(hours=2)
    print(f"相对时间: {time_ago(past_time)}")
    
    # 测试分批处理
    items = list(range(10))
    batches = batch_items(items, 3)
    print(f"分批结果: {batches}")