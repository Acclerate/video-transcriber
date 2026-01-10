"""
文件服务
处理文件相关的操作
"""

import os
import asyncio
import mimetypes
import re
from pathlib import Path
from typing import Optional, Callable

from loguru import logger

from config import settings


class FileService:
    """
    文件服务
    处理文件验证、格式检查等
    """

    def __init__(self, config: Optional[settings] = None):
        """
        初始化文件服务

        Args:
            config: 应用配置
        """
        self.config = config or settings
        logger.debug("文件服务初始化完成")

    # ============================================================
    # 文件验证
    # ============================================================

    def is_supported_video_file(self, file_path: str) -> bool:
        """
        检查是否为支持的视频文件

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否支持
        """
        ext = Path(file_path).suffix.lower()
        return ext in self.config.VIDEO_FORMATS

    def is_supported_audio_file(self, file_path: str) -> bool:
        """
        检查是否为支持的音频文件

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否支持
        """
        ext = Path(file_path).suffix.lower()
        return ext in self.config.AUDIO_FORMATS

    def is_supported_file(self, file_path: str) -> bool:
        """
        检查是否为支持的文件（视频或音频）

        Args:
            file_path: 文件路径

        Returns:
            bool: 是否支持
        """
        return (
            self.is_supported_video_file(file_path) or
            self.is_supported_audio_file(file_path)
        )

    async def validate_file(
        self,
        file_path: str,
        max_size_mb: Optional[int] = None
    ) -> tuple[bool, Optional[str]]:
        """
        验证文件

        Args:
            file_path: 文件路径
            max_size_mb: 最大文件大小（MB）

        Returns:
            tuple[bool, Optional[str]]: (是否有效, 错误消息)
        """
        path = Path(file_path)

        # 检查文件是否存在
        if not path.exists():
            return False, "文件不存在"

        # 检查是否为文件
        if not path.is_file():
            return False, "路径不是文件"

        # 检查文件格式
        if not self.is_supported_file(file_path):
            return False, f"不支持的文件格式: {path.suffix}"

        # 检查文件大小
        file_size = path.stat().st_size
        max_size = (max_size_mb or self.config.MAX_FILE_SIZE) * 1024 * 1024
        if file_size > max_size:
            return False, f"文件大小超过限制 ({max_size / 1024 / 1024}MB)"

        # 检查文件是否为空
        if file_size == 0:
            return False, "文件为空"

        return True, None

    def get_file_info(self, file_path: str) -> dict:
        """
        获取文件信息

        Args:
            file_path: 文件路径

        Returns:
            dict: 文件信息
        """
        path = Path(file_path)

        if not path.exists():
            return {}

        stat = path.stat()

        return {
            "name": path.name,
            "stem": path.stem,
            "suffix": path.suffix,
            "size": stat.st_size,
            "size_mb": round(stat.st_size / 1024 / 1024, 2),
            "created": stat.st_ctime,
            "modified": stat.st_mtime,
            "is_video": self.is_supported_video_file(file_path),
            "is_audio": self.is_supported_audio_file(file_path),
            "mime_type": mimetypes.guess_type(file_path)[0],
        }

    # ============================================================
    # 文件操作
    # ============================================================

    def ensure_directory(self, directory: str) -> Path:
        """
        确保目录存在

        Args:
            directory: 目录路径

        Returns:
            Path: 目录路径对象
        """
        dir_path = Path(directory)
        dir_path.mkdir(parents=True, exist_ok=True)
        return dir_path

    def get_safe_filename(self, filename: str, max_length: int = 255) -> str:
        """
        获取安全的文件名

        Args:
            filename: 原始文件名
            max_length: 最大长度

        Returns:
            str: 安全的文件名
        """
        # 移除非法字符
        illegal_chars = r'[<>:"/\\|?*]'
        safe_name = re.sub(illegal_chars, '_', filename)

        # 移除控制字符
        safe_name = ''.join(char for char in safe_name if ord(char) >= 32)

        # 限制长度
        if len(safe_name) > max_length:
            name, ext = os.path.splitext(safe_name)
            max_name_length = max_length - len(ext)
            safe_name = name[:max_name_length] + ext

        # 去除首尾空格和点号
        safe_name = safe_name.strip(' .')

        return safe_name or "untitled"

    def get_unique_filepath(
        self,
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

    async def copy_file(
        self,
        src: str,
        dst: str,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> str:
        """
        异步复制文件

        Args:
            src: 源文件路径
            dst: 目标文件路径
            progress_callback: 进度回调函数

        Returns:
            str: 目标文件路径
        """
        src_path = Path(src)
        dst_path = Path(dst)

        # 确保目标目录存在
        dst_path.parent.mkdir(parents=True, exist_ok=True)

        # 获取文件大小
        file_size = src_path.stat().st_size
        copied = 0

        # 异步复制
        async with asyncio.Lock():
            with open(src_path, 'rb') as src_file:
                with open(dst_path, 'wb') as dst_file:
                    while True:
                        chunk = src_file.read(8192)
                        if not chunk:
                            break
                        dst_file.write(chunk)
                        copied += len(chunk)

                        if progress_callback:
                            progress = (copied / file_size) * 100
                            progress_callback(progress)

        return str(dst_path)

    # ============================================================
    # 清理操作
    # ============================================================

    async def cleanup_directory(
        self,
        directory: str,
        older_than_seconds: int = 3600,
        pattern: str = "*"
    ) -> int:
        """
        清理目录中的旧文件

        Args:
            directory: 目录路径
            older_than_seconds: 文件年龄（秒）
            pattern: 文件匹配模式

        Returns:
            int: 清理的文件数量
        """
        import time

        dir_path = Path(directory)
        if not dir_path.exists():
            return 0

        current_time = time.time()
        cleaned_count = 0

        for file_path in dir_path.glob(pattern):
            if file_path.is_file():
                file_age = current_time - file_path.stat().st_mtime
                if file_age > older_than_seconds:
                    try:
                        file_path.unlink()
                        cleaned_count += 1
                        logger.debug(f"清理文件: {file_path}")
                    except Exception as e:
                        logger.warning(f"清理文件失败: {file_path}, {e}")

        logger.info(f"清理了 {cleaned_count} 个文件")
        return cleaned_count

    def get_directory_size(self, directory: str) -> int:
        """
        获取目录大小

        Args:
            directory: 目录路径

        Returns:
            int: 目录大小（字节）
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            return 0

        total_size = 0
        for file_path in dir_path.rglob('*'):
            if file_path.is_file():
                total_size += file_path.stat().st_size

        return total_size
