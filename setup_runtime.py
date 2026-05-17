#!/usr/bin/env python3
"""
运行时自动安装脚本 — 联网环境轻量版

在联网环境下，首次启动时自动下载缺失的 FFmpeg 和 SenseVoice 模型。
由 start.sh / start_server.bat 在启动 uvicorn 前调用。

用法:
    python setup_runtime.py          # 下载所有缺失组件
    python setup_runtime.py --check  # 仅检查不下载，返回 0=已就绪 1=缺失
"""

import os
import sys
from pathlib import Path


def _get_root() -> Path:
    """获取包根目录（setup_runtime.py 在 app/ 下，根目录在上层）"""
    return Path(__file__).resolve().parent.parent


# ============================================================
# 下载工具
# ============================================================

def _download(url: str, dest: Path, desc: str = "", retries: int = 3) -> None:
    """下载文件带进度显示和重试"""
    import urllib.request
    import time

    if dest.exists():
        print(f"  [跳过] 已存在: {dest.name}")
        return

    label = desc or dest.name
    print(f"  下载 {label} ...")
    dest.parent.mkdir(parents=True, exist_ok=True)

    def _hook(count, block_size, total_size):
        if total_size > 0:
            pct = min(count * block_size / total_size * 100, 100)
            sys.stdout.write(f"\r  进度: {pct:.1f}% ")
            sys.stdout.flush()

    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlretrieve(url, str(dest), reporthook=_hook)
            sys.stdout.write("\r  进度: 100%   \n")
            break
        except Exception as e:
            if dest.exists():
                dest.unlink()
            if attempt < retries:
                print(f"\n  重试 ({attempt}/{retries}) ...")
                time.sleep(2 * attempt)
            else:
                raise RuntimeError(f"下载失败 ({retries}次): {label} - {e}") from e

    print(f"  完成: {dest}")


# ============================================================
# FFmpeg
# ============================================================

FFMPEG_WINDOWS_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_LINUX_URL = (
    "https://johnvansickle.com/ffmpeg/releases/"
    "ffmpeg-release-amd64-static.tar.xz"
)


def _is_windows() -> bool:
    return sys.platform.startswith("win")


def ensure_ffmpeg() -> bool:
    """检查 FFmpeg，缺失则下载。返回 True 表示可用"""
    import platform
    import shutil

    root = _get_root()
    ffmpeg_dir = root / "ffmpeg"
    exe_name = "ffmpeg.exe" if _is_windows() else "ffmpeg"
    ffmpeg_path = ffmpeg_dir / exe_name

    if ffmpeg_path.exists():
        print("  [检查] FFmpeg: 已就绪")
        return True

    # 再检查系统 PATH
    if shutil.which("ffmpeg"):
        print("  [检查] FFmpeg: 已在系统 PATH 中")
        return True

    print("  [检查] FFmpeg: 未找到，开始下载 ...")
    ffmpeg_dir.mkdir(parents=True, exist_ok=True)

    if _is_windows():
        return _ensure_ffmpeg_windows(ffmpeg_dir)
    else:
        return _ensure_ffmpeg_linux(ffmpeg_dir)


def _ensure_ffmpeg_windows(ffmpeg_dir: Path) -> bool:
    """Windows: 下载并解压 FFmpeg"""
    import zipfile
    import shutil

    archive = ffmpeg_dir / "ffmpeg_essentials.zip"
    _download(FFMPEG_WINDOWS_URL, archive, "FFmpeg (Windows)")

    extract_dir = ffmpeg_dir / "_extract"
    extract_dir.mkdir(exist_ok=True)
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(extract_dir)

        for root, dirs, files in os.walk(extract_dir):
            if "ffmpeg.exe" in files:
                shutil.copy2(Path(root) / "ffmpeg.exe", ffmpeg_dir / "ffmpeg.exe")
                if "ffprobe.exe" in files:
                    shutil.copy2(Path(root) / "ffprobe.exe", ffmpeg_dir / "ffprobe.exe")
                break
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if archive.exists():
            archive.unlink()

    ok = (ffmpeg_dir / "ffmpeg.exe").exists()
    print(f"  [完成] FFmpeg: {'已安装' if ok else '提取失败'}")
    return ok


def _ensure_ffmpeg_linux(ffmpeg_dir: Path) -> bool:
    """Linux: 下载并解压 FFmpeg 静态二进制"""
    import tarfile
    import shutil

    archive = ffmpeg_dir / "ffmpeg_static.tar.xz"
    _download(FFMPEG_LINUX_URL, archive, "FFmpeg (Linux)")

    extract_dir = ffmpeg_dir / "_extract"
    extract_dir.mkdir(exist_ok=True)
    try:
        with tarfile.open(str(archive), "r:xz") as tf:
            tf.extractall(str(extract_dir))

        for root, dirs, files in os.walk(extract_dir):
            for fname in files:
                if fname == "ffmpeg":
                    shutil.copy2(Path(root) / "ffmpeg", ffmpeg_dir / "ffmpeg")
                elif fname == "ffprobe":
                    shutil.copy2(Path(root) / "ffprobe", ffmpeg_dir / "ffprobe")
    finally:
        shutil.rmtree(extract_dir, ignore_errors=True)
        if archive.exists():
            archive.unlink()

    for name in ("ffmpeg", "ffprobe"):
        p = ffmpeg_dir / name
        if p.exists():
            try:
                p.chmod(0o755)
            except Exception:
                pass

    ok = (ffmpeg_dir / "ffmpeg").exists()
    print(f"  [完成] FFmpeg: {'已安装' if ok else '提取失败'}")
    return ok


# ============================================================
# SenseVoice 模型
# ============================================================

def ensure_model() -> bool:
    """检查 SenseVoice 模型，缺失则下载。返回 True 表示可用"""
    root = _get_root()
    models_cache = root / "models_cache"
    model_marker = models_cache / "iic" / "SenseVoiceSmall"

    if model_marker.exists() and any(model_marker.rglob("*.pt")):
        print("  [检查] SenseVoice 模型: 已就绪")
        return True

    print("  [检查] SenseVoice 模型: 未找到，开始下载 ...")
    models_cache.mkdir(parents=True, exist_ok=True)

    try:
        from modelscope import snapshot_download

        print("  从 ModelScope 下载 iic/SenseVoiceSmall ...")
        old_cache = os.environ.get("MODELSCOPE_CACHE")
        os.environ["MODELSCOPE_CACHE"] = str(models_cache)
        try:
            model_dir = snapshot_download(
                "iic/SenseVoiceSmall", cache_dir=str(models_cache)
            )
            print(f"  完成: {model_dir}")
        finally:
            if old_cache:
                os.environ["MODELSCOPE_CACHE"] = old_cache
            else:
                os.environ.pop("MODELSCOPE_CACHE", None)

        ok = model_marker.exists() and any(model_marker.rglob("*.pt"))
        print(f"  [完成] SenseVoice 模型: {'已安装' if ok else '下载失败'}")
        return ok
    except ImportError:
        print("  [错误] 未安装 modelscope 库 (应已包含在依赖中)")
        return False
    except Exception as e:
        print(f"  [错误] 模型下载失败: {e}")
        return False


# ============================================================
# 主入口
# ============================================================

def main():
    """顺序检查并安装缺失的组件"""
    print("")
    print("  ============================================")
    print("    Video Transcriber - 运行环境检查")
    print("  ============================================")
    print("")

    all_ok = True

    print("  [1/2] FFmpeg ...")
    ok = ensure_ffmpeg()
    if not ok:
        all_ok = False
    print("")

    print("  [2/2] SenseVoice 模型 ...")
    ok = ensure_model()
    if not ok:
        all_ok = False
    print("")

    if all_ok:
        print("  ✓ 所有组件已就绪\n")
    else:
        print("  ⚠ 部分组件安装失败，服务可能无法正常运行\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    if "--check" in sys.argv[1:]:
        ffmpeg_ok = ensure_ffmpeg()
        model_ok = ensure_model()
        sys.exit(0 if (ffmpeg_ok and model_ok) else 1)
    else:
        sys.exit(main())