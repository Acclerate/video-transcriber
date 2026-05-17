"""
FFmpeg 检测模块
提供 FFmpeg 安装检测和版本获取功能
"""

import os
import shutil
import subprocess
import platform
from pathlib import Path
from typing import Optional

from loguru import logger

# 防止重复将 ffmpeg 目录添加到 PATH
_path_configured = False

# 平台特定的可执行文件名
if platform.system() == "Windows":
    _FFMPEG_EXE = "ffmpeg.exe"
    _FFPROBE_EXE = "ffprobe.exe"
else:
    _FFMPEG_EXE = "ffmpeg"
    _FFPROBE_EXE = "ffprobe"

# 捆绑 FFmpeg 目录（相对于项目根目录）
_BUNDLED_FFMPEG_DIR = Path(__file__).resolve().parent.parent.parent / "ffmpeg"

# 开发者本地路径
_DEV_FFMPEG_DIRS = [
    Path("D:/tools/ffmpeg-8.1-essentials_build/bin"),
]


def _find_local_ffmpeg(name: str) -> Optional[str]:
    """查找 ffmpeg/ffprobe：捆绑目录 → 相对目录 → 开发者路径"""
    # 1. 捆绑目录（便携部署）
    bundled = _BUNDLED_FFMPEG_DIR / name
    if bundled.exists():
        return str(bundled)

    # 2. 相对于当前工作目录（便携部署的另一种布局）
    cwd_bundled = Path("ffmpeg") / name
    if cwd_bundled.exists():
        return str(cwd_bundled.resolve())

    # 3. 开发者本地路径
    for d in _DEV_FFMPEG_DIRS:
        exe = d / name
        if exe.exists():
            return str(exe)

    return None


def get_ffmpeg_path() -> Optional[str]:
    """获取 ffmpeg 可执行文件路径（捆绑优先，回退到 PATH）"""
    local = _find_local_ffmpeg(_FFMPEG_EXE)
    if local:
        return local
    return shutil.which(_FFMPEG_EXE)


def get_ffprobe_path() -> Optional[str]:
    """获取 ffprobe 可执行文件路径（捆绑优先，回退到 PATH）"""
    local = _find_local_ffmpeg(_FFPROBE_EXE)
    if local:
        return local
    return shutil.which(_FFPROBE_EXE)


def check_ffmpeg_installed() -> bool:
    """
    检查 FFmpeg 是否已安装

    Returns:
        bool: FFmpeg 是否可用
    """
    return get_ffmpeg_path() is not None


def configure_pydub_ffmpeg() -> None:
    """
    将 FFmpeg 的完整路径设置给 pydub，
    并将 ffmpeg 目录添加到 PATH 环境变量，
    确保 FunASR/torchaudio 等库也能找到 ffmpeg。
    """
    global _path_configured
    try:
        from pydub.audio_segment import AudioSegment

        ffmpeg_path = get_ffmpeg_path()
        if ffmpeg_path:
            AudioSegment.converter = ffmpeg_path
            logger.debug(f"pydub converter 设置为: {ffmpeg_path}")

            # 将 ffmpeg 所在目录添加到 PATH（仅执行一次）
            if not _path_configured:
                ffmpeg_dir = str(Path(ffmpeg_path).parent)
                path_dirs = os.environ.get("PATH", "").split(os.pathsep)
                if ffmpeg_dir not in path_dirs:
                    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")
                    logger.info(f"已将 ffmpeg 目录添加到 PATH: {ffmpeg_dir}")
                _path_configured = True

        ffprobe_path = get_ffprobe_path()
        if ffprobe_path and hasattr(AudioSegment, 'ffprobe'):
            AudioSegment.ffprobe = ffprobe_path
            logger.debug(f"pydub ffprobe 设置为: {ffprobe_path}")
    except Exception as e:
        logger.warning(f"配置 pydub FFmpeg 路径失败: {e}")


def get_ffmpeg_version() -> Optional[str]:
    """
    获取 FFmpeg 版本信息

    Returns:
        Optional[str]: FFmpeg 版本信息，失败返回 None
    """
    try:
        ffmpeg = get_ffmpeg_path() or "ffmpeg"
        result = subprocess.run(
            [ffmpeg, "-version"],
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
  • 从音视频文件中提取音频
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
