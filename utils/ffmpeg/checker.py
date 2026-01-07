"""
FFmpeg 检测模块
提供 FFmpeg 安装检测和版本获取功能
"""

import shutil
import subprocess
import platform
from typing import Optional

from loguru import logger


def check_ffmpeg_installed() -> bool:
    """
    检查 FFmpeg 是否已安装

    Returns:
        bool: FFmpeg 是否可用
    """
    return shutil.which("ffmpeg") is not None


def get_ffmpeg_version() -> Optional[str]:
    """
    获取 FFmpeg 版本信息

    Returns:
        Optional[str]: FFmpeg 版本信息，失败返回 None
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            # 返回第一行基本信息
            first_line = result.stdout.split('\n')[0]
            return first_line
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        logger.debug(f"获取 FFmpeg 版本失败: {e}")
        return None


def get_ffmpeg_install_command() -> str:
    """
    根据当前操作系统获取 FFmpeg 安装命令

    Returns:
        str: 安装命令
    """
    system = platform.system()
    machine = platform.machine()

    if system == "Linux":
        # 检测 Linux 发行版
        try:
            with open("/etc/os-release", "r") as f:
                os_release = f.read().lower()
                if "ubuntu" in os_release or "debian" in os_release:
                    return "sudo apt update && sudo apt install -y ffmpeg"
                elif "centos" in os_release or "rhel" in os_release or "fedora" in os_release:
                    return "sudo yum install -y ffmpeg"
                elif "arch" in os_release:
                    return "sudo pacman -S ffmpeg"
        except Exception:
            pass
        return "sudo apt install -y ffmpeg  # Ubuntu/Debian"

    elif system == "Darwin":  # macOS
        return "brew install ffmpeg"

    elif system == "Windows":
        if machine.endswith("64"):
            return (
                "1. 下载 FFmpeg: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip\n"
                "2. 解压并添加到 PATH 环境变量"
            )
        else:
            return (
                "1. 下载 32位 FFmpeg: https://ffmpeg.org/download.html\n"
                "2. 解压并添加到 PATH 环境变量"
            )

    return "请访问 https://ffmpeg.org/download.html 获取安装指南"


def get_ffmpeg_help_message() -> str:
    """
    获取 FFmpeg 安装帮助信息

    Returns:
        str: 帮助信息
    """
    system = platform.system()
    install_cmd = get_ffmpeg_install_command()

    message = f"""
╔════════════════════════════════════════════════════════════════╗
║                     FFmpeg 未安装或不可用                        ║
╚════════════════════════════════════════════════════════════════╝

检测到系统 ({system}) 未安装 FFmpeg 或 FFmpeg 未在 PATH 中。

【为什么要安装 FFmpeg？】
FFmpeg 是处理音视频的核心工具，本项目使用它来：
  • 从视频文件中提取音频
  • 转换音频格式
  • 优化音频质量以提高转录准确率

【安装方法】
{install_cmd}

【验证安装】
安装完成后，请运行以下命令验证：
  ffmpeg -version

如果看到版本信息，说明安装成功！

【手动下载】
如果上述方法无法安装，请访问：
  https://ffmpeg.org/download.html

───────────────────────────────────────────────────────────────────
"""
    return message


def check_dependencies() -> tuple[bool, list[str]]:
    """
    检查所有必需的依赖

    Returns:
        tuple[bool, list[str]]: (是否全部可用, 缺失的依赖列表)
    """
    missing = []

    if not check_ffmpeg_installed():
        missing.append("FFmpeg")

    return len(missing) == 0, missing
