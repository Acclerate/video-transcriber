#!/usr/bin/env python3
"""
Video Transcriber - 便携式部署包构建脚本

用法:
    python scripts/build_portable.py --platform windows
    python scripts/build_portable.py --platform linux
    python scripts/build_portable.py --platform windows --skip-model --skip-compress
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import zipfile
from pathlib import Path

# ============================================================
# 配置常量
# ============================================================

PYTHON_VERSION = "3.10.11"
PYTHON_EMBED_URL = (
    f"https://www.python.org/ftp/python/{PYTHON_VERSION}"
    f"/python-{PYTHON_VERSION}-embed-amd64.zip"
)
PIP_INSTALLER_URL = "https://bootstrap.pypa.io/get-pip.py"

FFMPEG_WINDOWS_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
FFMPEG_LINUX_URL = (
    "https://johnvansickle.com/ffmpeg/releases/"
    "ffmpeg-release-amd64-static.tar.xz"
)

BOOTSTRAP_CSS_URL = (
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css"
)
BOOTSTRAP_JS_URL = (
    "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"
)
BOOTSTRAP_ICONS_CSS_URL = (
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css"
)
BOOTSTRAP_ICONS_FONT_URL = (
    "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/fonts/bootstrap-icons.woff2"
)

MANROPE_FONT_URLS = {
    400: "https://fonts.gstatic.com/s/manrope/v20/xn7_YHE41ni1AdIRqAuZuw1Bx9mbZk79FO_F.ttf",
    500: "https://fonts.gstatic.com/s/manrope/v20/xn7_YHE41ni1AdIRqAuZuw1Bx9mbZk7PFO_F.ttf",
    600: "https://fonts.gstatic.com/s/manrope/v20/xn7_YHE41ni1AdIRqAuZuw1Bx9mbZk4jE-_F.ttf",
    700: "https://fonts.gstatic.com/s/manrope/v20/xn7_YHE41ni1AdIRqAuZuw1Bx9mbZk4aE-_F.ttf",
    800: "https://fonts.gstatic.com/s/manrope/v20/xn7_YHE41ni1AdIRqAuZuw1Bx9mbZk59E-_F.ttf",
}

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_BASE = PROJECT_ROOT / "dist"
DOWNLOAD_CACHE = PROJECT_ROOT / "dist" / ".cache"

# 需要从 requirements.txt 中排除的包（构建时单独安装或不需要）
SKIP_PACKAGES = {
    "torch", "torchaudio",
    "pytest", "pytest-asyncio", "pytest-mock", "pytest-cov",
    "black", "isort", "flake8", "mypy",
}


# ============================================================
# 工具函数
# ============================================================

def download_file(url: str, dest: Path, desc: str = "", retries: int = 3) -> None:
    """下载文件，带全局缓存和重试"""
    if dest.exists():
        print(f"  [跳过] 已存在: {dest.name}")
        return

    # 检查全局下载缓存
    url_hash = hex(hash(url) & 0xFFFFFFFF)[2:]
    cache_file = DOWNLOAD_CACHE / url_hash / dest.name
    if cache_file.exists():
        print(f"  [缓存命中] {desc or dest.name}")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cache_file, dest)
        return

    label = desc or dest.name
    print(f"  下载 {label} ...")
    dest.parent.mkdir(parents=True, exist_ok=True)

    def _reporthook(count, block_size, total_size):
        if total_size > 0:
            pct = min(count * block_size / total_size * 100, 100)
            sys.stdout.write(f"\r  进度: {pct:.1f}% ")
            sys.stdout.flush()

    for attempt in range(1, retries + 1):
        try:
            urllib.request.urlretrieve(url, str(dest), reporthook=_reporthook)
            sys.stdout.write("\r  进度: 100%   \n")
            break
        except Exception as e:
            if dest.exists():
                dest.unlink()
            if attempt < retries:
                print(f"\n  重试 ({attempt}/{retries}) ...")
                import time; time.sleep(2 * attempt)
            else:
                raise RuntimeError(f"下载失败 ({retries}次): {label} - {e}") from e

    # 存入缓存
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(dest, cache_file)

    print(f"  完成: {dest}")


def run_cmd(cmd, **kwargs):
    """运行命令，打印并检查返回值"""
    print(f"  > {' '.join(str(c) for c in cmd)}")
    env = kwargs.pop("env", os.environ).copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(cmd, check=True, env=env, **kwargs)


# ============================================================
# 构建步骤
# ============================================================

def create_directory_structure(output_dir: Path) -> dict:
    """[Step 1] 创建输出目录结构"""
    dirs = {
        "root": output_dir,
        "python": output_dir / "python",
        "ffmpeg": output_dir / "ffmpeg",
        "app": output_dir / "app",
        "models_cache": output_dir / "models_cache",
        "temp": output_dir / "temp",
        "logs": output_dir / "logs",
        "output": output_dir / "output",
    }
    for d in dirs.values():
        d.mkdir(parents=True, exist_ok=True)

    app_subdirs = [
        "api", "api/routes",
        "core", "services", "models", "config",
        "utils", "utils/ffmpeg", "utils/audio", "utils/logging",
        "utils/file", "utils/common",
        "web", "web/vendor",
        "web/vendor/bootstrap/css",
        "web/vendor/bootstrap-icons/font",
    ]
    for sub in app_subdirs:
        (dirs["app"] / sub).mkdir(parents=True, exist_ok=True)

    return dirs


def setup_python_windows(python_dir: Path) -> None:
    """[Step 2a] Windows: 下载嵌入式 Python + 安装 pip"""
    embed_zip = python_dir / "python_embed.zip"

    download_file(PYTHON_EMBED_URL, embed_zip, "Python 3.10 Embedded")

    with zipfile.ZipFile(embed_zip, "r") as zf:
        zf.extractall(python_dir)
    embed_zip.unlink()

    # 修改 python310._pth 启用 site-packages
    pth_file = python_dir / "python310._pth"
    if pth_file.exists():
        content = pth_file.read_text(encoding="utf-8")
        content = content.replace("#import site", "import site")
        if "Lib\\site-packages" not in content:
            content += "Lib\\site-packages\n"
        pth_file.write_text(content, encoding="utf-8")

    site_packages = python_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)

    # 安装 pip
    get_pip = python_dir / "get-pip.py"
    download_file(PIP_INSTALLER_URL, get_pip, "pip installer")
    run_cmd([str(python_dir / "python.exe"), str(get_pip), "--no-warn-script-location"])
    get_pip.unlink()


def setup_python_linux(python_dir: Path, cross_build: bool) -> None:
    """[Step 2b] Linux: 创建 venv（本机构建）或留空（交叉构建）"""
    if cross_build:
        print("  [交叉构建] Python 环境将在目标机器上由 setup.sh 安装")
        return

    venv_python = python_dir / "bin" / "python"
    if venv_python.exists():
        print("  [跳过] venv 已存在")
        return

    system_python = shutil.which("python3") or shutil.which("python")
    if not system_python:
        raise RuntimeError("未找到 Python3，请先安装 python3")

    run_cmd([system_python, "-m", "venv", str(python_dir)])
    run_cmd([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])


def install_requirements(python_dir: Path, target_platform: str,
                         cross_build: bool) -> None:
    """[Step 3] 安装 Python 依赖（CPU-only PyTorch）"""
    if cross_build:
        print("  [交叉构建] 依赖将在目标机器上由 setup.sh 安装")
        # 复制 requirements.txt 供 setup.sh 使用
        shutil.copy2(PROJECT_ROOT / "requirements.txt", python_dir / "requirements.txt")
        return

    python_exe = (
        str(python_dir / "python.exe")
        if target_platform == "windows"
        else str(python_dir / "bin" / "python")
    )

    # 先安装 CPU 版 PyTorch（使用 pip 缓存加速重复构建）
    print("  安装 CPU 版 PyTorch ...")
    run_cmd([
        python_exe, "-m", "pip", "install",
        "torch", "torchaudio",
        "--index-url", "https://download.pytorch.org/whl/cpu",
    ])

    # 过滤 requirements.txt（排除 torch 和开发工具）
    req_file = PROJECT_ROOT / "requirements.txt"
    filtered = python_dir / "_requirements_filtered.txt"
    with open(req_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    kept = []
    for line in lines:
        stripped = line.strip().lower()
        if not stripped or stripped.startswith("#"):
            continue
        pkg = stripped.split("==")[0].split(">=")[0].split("[")[0].strip()
        if pkg not in SKIP_PACKAGES:
            kept.append(line)

    with open(filtered, "w", encoding="utf-8") as f:
        f.writelines(kept)

    print("  安装其余依赖 ...")
    run_cmd([
        python_exe, "-m", "pip", "install",
        "-r", str(filtered),
    ])
    filtered.unlink()


def download_ffmpeg_windows(ffmpeg_dir: Path) -> None:
    """[Step 4a] Windows: 下载 FFmpeg"""
    if (ffmpeg_dir / "ffmpeg.exe").exists():
        print("  [跳过] ffmpeg.exe 已存在")
        return

    ffmpeg_zip = ffmpeg_dir / "ffmpeg_essentials.zip"
    download_file(FFMPEG_WINDOWS_URL, ffmpeg_zip, "FFmpeg Essentials")

    # 解压并查找 bin 目录
    with zipfile.ZipFile(ffmpeg_zip, "r") as zf:
        zf.extractall(ffmpeg_dir / "_extracted")
    ffmpeg_zip.unlink()

    # 在解压目录中查找 ffmpeg.exe
    for root, dirs, files in os.walk(ffmpeg_dir / "_extracted"):
        if "ffmpeg.exe" in files:
            shutil.copy2(Path(root) / "ffmpeg.exe", ffmpeg_dir / "ffmpeg.exe")
            if "ffprobe.exe" in files:
                shutil.copy2(Path(root) / "ffprobe.exe", ffmpeg_dir / "ffprobe.exe")
            break

    shutil.rmtree(ffmpeg_dir / "_extracted", ignore_errors=True)

    if not (ffmpeg_dir / "ffmpeg.exe").exists():
        raise RuntimeError("未能从压缩包中提取 ffmpeg.exe")


def download_ffmpeg_linux(ffmpeg_dir: Path) -> None:
    """[Step 4b] Linux: 下载 FFmpeg 静态二进制"""
    if (ffmpeg_dir / "ffmpeg").exists():
        print("  [跳过] ffmpeg 已存在")
        return

    ffmpeg_tar = ffmpeg_dir / "ffmpeg_static.tar.xz"
    download_file(FFMPEG_LINUX_URL, ffmpeg_tar, "FFmpeg Static (Linux)")

    # 解压（使用 Python tarfile，兼容 Windows 交叉构建）
    extract_dir = ffmpeg_dir / "_extracted"
    extract_dir.mkdir(exist_ok=True)

    import tarfile
    with tarfile.open(str(ffmpeg_tar), "r:xz") as tf:
        tf.extractall(str(extract_dir))
    ffmpeg_tar.unlink()

    # 查找 ffmpeg 和 ffprobe 二进制
    for root, dirs, files in os.walk(extract_dir):
        for fname in files:
            if fname == "ffmpeg":
                shutil.copy2(Path(root) / "ffmpeg", ffmpeg_dir / "ffmpeg")
            elif fname == "ffprobe":
                shutil.copy2(Path(root) / "ffprobe", ffmpeg_dir / "ffprobe")

    shutil.rmtree(extract_dir, ignore_errors=True)

    if not (ffmpeg_dir / "ffmpeg").exists():
        raise RuntimeError("未能从压缩包中提取 ffmpeg")

    try:
        (ffmpeg_dir / "ffmpeg").chmod(0o755)
        if (ffmpeg_dir / "ffprobe").exists():
            (ffmpeg_dir / "ffprobe").chmod(0o755)
    except Exception:
        pass  # Windows 上 chmod 无效但不影响


def copy_app_source(app_dir: Path) -> None:
    """[Step 5] 复制项目源码"""
    source_dirs = ["api", "core", "services", "models", "config", "utils", "web"]
    source_files = ["webmain.py", "setup_runtime.py"]

    for d in source_dirs:
        src = PROJECT_ROOT / d
        dst = app_dir / d
        if not src.exists():
            continue
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(
            src, dst,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )

    for f in source_files:
        src = PROJECT_ROOT / f
        if src.exists():
            shutil.copy2(src, app_dir / f)


def bundle_web_assets(app_dir: Path) -> None:
    """[Step 6] 下载 Bootstrap + 字体离线资源 + 修补 index.html"""
    vendor = app_dir / "web" / "vendor"
    bootstrap_css_dir = vendor / "bootstrap" / "css"
    bootstrap_icons_dir = vendor / "bootstrap-icons" / "font"
    fonts_dir = vendor / "fonts"

    for d in [bootstrap_css_dir, bootstrap_icons_dir, fonts_dir]:
        d.mkdir(parents=True, exist_ok=True)

    download_file(BOOTSTRAP_CSS_URL, bootstrap_css_dir / "bootstrap.min.css", "Bootstrap CSS")
    download_file(BOOTSTRAP_JS_URL, vendor / "bootstrap" / "bootstrap.bundle.min.js", "Bootstrap JS")
    download_file(BOOTSTRAP_ICONS_CSS_URL, vendor / "bootstrap-icons" / "bootstrap-icons.css", "Bootstrap Icons CSS")
    download_file(BOOTSTRAP_ICONS_FONT_URL, bootstrap_icons_dir / "bootstrap-icons.woff2", "Bootstrap Icons Font")

    # 下载 Manrope 字体
    for weight, url in MANROPE_FONT_URLS.items():
        download_file(url, fonts_dir / f"manrope-{weight}.ttf", f"Manrope {weight}")

    # 生成本地字体 CSS（Manrope 本地 + Noto Sans SC 系统 fallback）
    fonts_css = fonts_dir / "fonts.css"
    if not fonts_css.exists():
        lines = []
        for weight in MANROPE_FONT_URLS:
            lines.append(
                f"@font-face {{ font-family: 'Manrope'; font-weight: {weight}; "
                f"font-display: swap; src: url('./manrope-{weight}.ttf') format('truetype'); }}"
            )
        fonts_css.write_text("\n".join(lines), encoding="utf-8")

    # 修补 index.html 使用本地资源
    html_file = app_dir / "web" / "index.html"
    if not html_file.exists():
        return

    content = html_file.read_text(encoding="utf-8")

    content = content.replace(
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css",
        "/static/vendor/bootstrap/css/bootstrap.min.css",
    )
    content = content.replace(
        "https://cdn.jsdelivr.net/npm/bootstrap-icons@1.10.0/font/bootstrap-icons.css",
        "/static/vendor/bootstrap-icons/bootstrap-icons.css",
    )
    content = content.replace(
        "https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js",
        "/static/vendor/bootstrap/bootstrap.bundle.min.js",
    )

    # 替换 Google Fonts 为本地字体
    import re
    content = re.sub(
        r'<link rel="preconnect" href="https://fonts\.gstatic\.com"[^>]*>\n?',
        '', content
    )
    content = re.sub(
        r'<link rel="preconnect" href="https://fonts\.googleapis\.com"[^>]*>\n?',
        '', content
    )
    content = re.sub(
        r'<link href="https://fonts\.googleapis\.com/css2[^"]*"[^>]*>',
        '<link href="/static/vendor/fonts/fonts.css" rel="stylesheet">', content
    )

    # 修正 Bootstrap Icons 字体路径（CSS 引用相对路径 ./fonts/）
    icons_css = vendor / "bootstrap-icons" / "bootstrap-icons.css"
    if icons_css.exists():
        css_content = icons_css.read_text(encoding="utf-8")
        css_content = css_content.replace(
            "./fonts/bootstrap-icons.woff2",
            "./font/bootstrap-icons.woff2",
        )
        icons_css.write_text(css_content, encoding="utf-8")

    html_file.write_text(content, encoding="utf-8")


def download_model(models_cache_dir: Path, app_dir: Path, python_dir: Path,
                   target_platform: str, cross_build: bool) -> None:
    """[Step 7] 预下载 SenseVoice 模型"""
    # 检查输出目录是否已有模型
    model_marker = models_cache_dir / "iic" / "SenseVoiceSmall"
    if model_marker.exists() and any(model_marker.rglob("*.pt")):
        print("  [跳过] 模型已存在")
        return

    if cross_build:
        print("  [交叉构建] 模型将在目标机器上由 setup.sh 下载")
        return

    # 先尝试从项目根目录复制已有模型
    src_model = PROJECT_ROOT / "models_cache" / "iic" / "SenseVoiceSmall"
    if src_model.exists() and any(src_model.rglob("*.pt")):
        print("  从本地缓存复制模型 ...")
        dst_model = models_cache_dir / "iic" / "SenseVoiceSmall"
        if dst_model.exists():
            shutil.rmtree(dst_model)
        shutil.copytree(src_model, dst_model)
        model_size = sum(f.stat().st_size for f in dst_model.rglob("*") if f.is_file())
        print(f"  完成: {model_size / (1024**2):.1f} MB")
        return

    python_exe = (
        str(python_dir / "python.exe")
        if target_platform == "windows"
        else str(python_dir / "bin" / "python")
    )

    env = {
        **os.environ,
        "MODELSCOPE_CACHE": str(models_cache_dir.resolve()),
        "PYTHONPATH": str(app_dir.resolve()),
    }

    run_cmd(
        [python_exe, str(app_dir / "webmain.py"),
         "--skip-deps-check", "download-model", "sensevoice-small"],
        env=env,
    )


def create_launchers(output_dir: Path, target_platform: str,
                     cross_build: bool) -> None:
    """[Step 8] 生成启动脚本"""
    templates = PROJECT_ROOT / "scripts" / "templates"

    if target_platform == "windows":
        for name in ["启动.bat", "start_server.bat", "停止.bat"]:
            src = templates / "windows" / name
            if src.exists():
                shutil.copy2(src, output_dir / name)
    else:
        for name in ["start.sh", "stop.sh"]:
            src = templates / "linux" / name
            if src.exists():
                dst = output_dir / name
                # 读取并转换为 LF 换行符
                content = src.read_text(encoding="utf-8")
                content = content.replace("\r\n", "\n").replace("\r", "\n")
                dst.write_text(content, encoding="utf-8", newline="\n")
                try:
                    dst.chmod(0o755)
                except Exception:
                    pass

        # 交叉构建时生成 setup.sh（在目标 Linux 机器上运行）
        if cross_build:
            _create_linux_setup_sh(output_dir)


def create_env_file(output_dir: Path, lite: bool = False) -> None:
    """[Step 8b] 生成 .env 配置文件"""
    env_content = """\
# Video Transcriber - 便携部署配置
HOST=0.0.0.0
PORT=8665
DEBUG=false

# 模型
DEFAULT_MODEL=sensevoice-small
DEFAULT_LANGUAGE=zh
ENABLE_GPU=false
MODEL_CACHE_DIR=./models_cache

# 音频分块
ENABLE_AUDIO_CHUNKING=true
CHUNK_DURATION_SECONDS=300
CHUNK_OVERLAP_SECONDS=1
MIN_DURATION_FOR_CHUNKING=30

# 文件路径
TEMP_DIR=./temp
OUTPUT_DIR=./output

# 日志
LOG_LEVEL=INFO
LOG_DIR=./logs
LOG_FILE=./logs/app.log
LOG_TO_CONSOLE=true

# 任务
MAX_CONCURRENT_TASKS=3
TASK_TIMEOUT=3600

# 运行时
AUTO_SETUP=true
"""
    (output_dir / ".env").write_text(env_content, encoding="utf-8")


def _create_linux_setup_sh(output_dir: Path) -> None:
    """交叉构建时生成 setup.sh，在目标 Linux 机器上运行以安装 Python 环境和模型"""
    setup_sh = output_dir / "setup.sh"
    content = """\
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo ""
echo "  ============================================"
echo "    Video Transcriber - 首次安装"
echo "  ============================================"
echo ""

# 检查 Python3
PYTHON3=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON3="$cmd"
        break
    fi
done

if [ -z "$PYTHON3" ]; then
    echo "[错误] 未找到 Python3，请先安装:"
    echo "  Ubuntu/Debian: sudo apt install python3 python3-venv python3-pip"
    echo "  CentOS/RHEL:   sudo yum install python3"
    exit 1
fi

echo "[1/3] 创建 Python 虚拟环境 ..."
$PYTHON3 -m venv "$SCRIPT_DIR/python"
PIP="$SCRIPT_DIR/python/bin/pip"
$PIP install --upgrade pip

echo "[2/3] 安装依赖 (CPU PyTorch + 项目依赖) ..."
$PIP install --no-cache-dir torch torchaudio \\
    --index-url https://download.pytorch.org/whl/cpu

# 安装其余依赖
REQ="$SCRIPT_DIR/python/requirements.txt"
if [ -f "$REQ" ]; then
    $PIP install --no-cache-dir -r "$REQ"
else
    $PIP install --no-cache-dir fastapi uvicorn pydantic pydantic-settings \\
        click rich loguru python-dotenv httpx pydub librosa slowapi \\
        funasr modelscope
fi

echo "[3/3] 下载 SenseVoice 模型 ..."
export PYTHONPATH="$SCRIPT_DIR/app"
export MODELSCOPE_CACHE="$SCRIPT_DIR/models_cache"
$SCRIPT_DIR/python/bin/python -c \\
    "from modelscope import snapshot_download; snapshot_download('iic/SenseVoiceSmall')"

echo ""
echo "  安装完成! 运行以下命令启动服务:"
echo "    ./start.sh"
echo ""
"""
    setup_sh.write_text(content, encoding="utf-8", newline="\n")
    try:
        setup_sh.chmod(0o755)
    except Exception:
        pass
    print("  已生成 setup.sh (在目标 Linux 机器上运行以完成安装)")


def compress_package(output_dir: Path, target_platform: str) -> Path:
    """[Step 9] 压缩打包"""
    if target_platform == "windows":
        archive_path = str(output_dir) + ".zip"
        print(f"  压缩为 {archive_path} ...")
        with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    file_path = Path(root) / file
                    arcname = file_path.relative_to(output_dir.parent)
                    zf.write(file_path, arcname)
        return Path(archive_path)
    else:
        archive_path = str(output_dir) + ".tar.gz"
        print(f"  压缩为 {archive_path} ...")
        with tarfile.open(archive_path, "w:gz") as tf:
            tf.add(str(output_dir), arcname=output_dir.name)
        return Path(archive_path)


# ============================================================
# 主流程
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="构建 Video Transcriber 便携部署包")
    parser.add_argument(
        "--platform", choices=["windows", "linux"],
        default="windows" if platform.system() == "Windows" else "linux",
        help="目标平台 (默认: 当前系统)",
    )
    parser.add_argument("--output-dir", type=str, default=None,
                        help="输出目录 (默认: ./dist/video-transcriber-{platform})")
    parser.add_argument("--skip-model", action="store_true",
                        help="跳过模型下载 (测试用)")
    parser.add_argument("--skip-compress", action="store_true",
                        help="跳过压缩")
    parser.add_argument("--skip-deps", action="store_true",
                        help="跳过 Python 环境和依赖安装（仍会补齐 FFmpeg/模型/资源）")
    parser.add_argument("--lite", action="store_true",
                        help="联网轻量版：跳过 FFmpeg 和模型下载，首次启动时自动拉取")
    args = parser.parse_args()

    target = args.platform
    current_os = platform.system().lower()
    cross_build = (
        (target == "linux" and current_os == "windows") or
        (target == "windows" and current_os == "linux")
    )

    output_dir = (
        Path(args.output_dir) if args.output_dir
        else OUTPUT_BASE / f"video-transcriber-{target}{'-lite' if args.lite else ''}"
    )

    print(f"")
    print(f"  ============================================")
    print(f"    Video Transcriber 便携包构建")
    print(f"    目标平台: {target}")
    if args.lite:
        print(f"    ** 联网轻量版 (首次运行自动下载 FFmpeg + 模型) **")
    if cross_build:
        print(f"    ** 交叉构建模式 **")
    if args.skip_deps:
        print(f"    ** 跳过 Python 环境和依赖安装 **")
    print(f"    输出目录: {output_dir}")
    print(f"  ============================================")
    print(f"")

    build_start = time.time()

    def _step(step_num, label, func, *args_func, **kwargs_func):
        """执行构建步骤并计时"""
        t0 = time.time()
        print(f"\n[{step_num}] {label} ...")
        func(*args_func, **kwargs_func)
        elapsed = time.time() - t0
        if elapsed >= 60:
            print(f"  ({elapsed:.0f}s = {elapsed/60:.1f}m)")
        else:
            print(f"  ({elapsed:.1f}s)")

    # Step 1
    dirs = create_directory_structure(output_dir)
    _step(1, "创建目录结构", lambda: None)

    if args.skip_deps:
        # 快速模式：跳过 Python 环境和依赖安装，仍补齐 FFmpeg/模型等运行资产
        print("\n[2-3] [跳过] Python 环境和依赖安装 (--skip-deps)")
    else:
        # Step 2
        if target == "windows":
            _step(2, "设置 Python 环境", setup_python_windows, dirs["python"])
        else:
            _step(2, "设置 Python 环境", setup_python_linux, dirs["python"], cross_build)

        # Step 3
        _step(3, "安装 Python 依赖 (CPU PyTorch)", install_requirements,
              dirs["python"], target, cross_build)

    # Step 4
    if args.lite:
        print("\n[4] [跳过] FFmpeg 下载 (--lite 模式，首次运行时自动安装)")
    elif target == "windows":
        _step(4, "下载 FFmpeg", download_ffmpeg_windows, dirs["ffmpeg"])
    else:
        _step(4, "下载 FFmpeg", download_ffmpeg_linux, dirs["ffmpeg"])

    # Step 5
    _step(5, "复制项目源码", copy_app_source, dirs["app"])

    # Step 6
    _step(6, "打包离线 Web 资源", bundle_web_assets, dirs["app"])

    # Step 7
    if args.lite:
        print("\n[7] [跳过] 模型下载 (--lite 模式，首次运行时自动安装)")
    elif not args.skip_model:
        _step(7, "下载 SenseVoice 模型", download_model,
              dirs["models_cache"], dirs["app"], dirs["python"],
              target, cross_build)
    else:
        print("\n[7] [跳过] 模型下载 (--skip-model)")

    # Step 8
    _step(8, "生成启动脚本和配置", create_launchers, output_dir, target, cross_build)
    create_env_file(output_dir, lite=args.lite)

    # Step 9
    if not args.skip_compress:
        t0 = time.time()
        print("\n[9] 压缩打包 ...")
        archive = compress_package(output_dir, target)
        archive_size = archive.stat().st_size / (1024 ** 3)
        elapsed = time.time() - t0
        print(f"  压缩包: {archive} ({archive_size:.2f} GB)")
        print(f"  ({elapsed:.1f}s)")
    else:
        print("\n[9] [跳过] 压缩 (--skip-compress)")

    # 统计
    total_time = time.time() - build_start
    try:
        du_result = subprocess.run(
            ["du", "-sb", str(output_dir)], capture_output=True, text=True, timeout=30
        )
        total_size = int(du_result.stdout.split()[0])
    except Exception:
        try:
            total_size = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
        except Exception:
            total_size = 0
    size_str = f"{total_size / (1024 ** 3):.2f} GB" if total_size else "unknown"
    print(f"\n  包大小: {size_str} (未压缩)")
    print(f"  总耗时: {total_time:.0f}s ({total_time/60:.1f}m)")
    print(f"\n  构建完成!")


if __name__ == "__main__":
    main()
