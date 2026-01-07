"""
文件操作辅助函数
"""

import os
import re
import hashlib
import asyncio
import mimetypes
from datetime import datetime
from pathlib import Path
from typing import Optional

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
    size_float = float(size_bytes)

    while size_float >= 1024.0 and i < len(size_names) - 1:
        size_float /= 1024.0
        i += 1

    return f"{size_float:.1f} {size_names[i]}"


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
    获取文件 MIME 类型

    Args:
        file_path: 文件路径

    Returns:
        Optional[str]: MIME 类型
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


def get_unique_filepath(
    directory: str,
    filename: str,
    extension: Optional[str] = None
) -> str:
    """
    获取唯一的文件路径

    Args:
        directory: 目录
        filename: 文件名
        extension: 扩展名（可选）

    Returns:
        str: 唯一的文件路径
    """
    dir_path = Path(directory)
    dir_path.mkdir(parents=True, exist_ok=True)

    if extension:
        if not extension.startswith('.'):
            extension = '.' + extension
        base_name = Path(filename).stem
        filename = base_name + extension

    filepath = dir_path / filename

    # 如果文件已存在，添加数字后缀
    counter = 1
    while filepath.exists():
        stem = Path(filename).stem
        ext = Path(filename).suffix
        new_filename = f"{stem}_{counter}{ext}"
        filepath = dir_path / new_filename
        counter += 1

    return str(filepath)
