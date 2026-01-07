#!/usr/bin/env python3
"""
快速验证 FFmpeg 检测功能
使用方法: python verify_ffmpeg.py
"""

# 检查 1: 验证模块导入
print("=" * 60)
print("检查 1: 验证模块导入")
print("=" * 60)

try:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))

    from utils.helpers import (
        check_ffmpeg_installed,
        get_ffmpeg_version,
        get_ffmpeg_install_command,
        get_ffmpeg_help_message,
        check_dependencies
    )
    print("✓ 模块导入成功\n")
except Exception as e:
    print(f"✗ 模块导入失败: {e}\n")
    sys.exit(1)

# 检查 2: 测试 FFmpeg 检测函数
print("=" * 60)
print("检查 2: 测试 FFmpeg 检测函数")
print("=" * 60)

# 检查 FFmpeg 是否安装
is_installed = check_ffmpeg_installed()
print(f"FFmpeg 已安装: {'是' if is_installed else '否'}")

# 获取 FFmpeg 版本
version = get_ffmpeg_version()
if version:
    print(f"FFmpeg 版本: {version.split()[2] if len(version.split()) > 2 else version}")
else:
    print("FFmpeg 版本: 无法获取")

# 获取安装命令
install_cmd = get_ffmpeg_install_command()
print(f"安装命令:\n{install_cmd}")

# 依赖检查
all_ok, missing = check_dependencies()
print(f"\n依赖检查: {'通过' if all_ok else f'失败 - 缺失: {missing}'}")

print()

# 检查 3: 显示帮助信息（如果 FFmpeg 未安装）
if not is_installed:
    print("=" * 60)
    print("FFmpeg 安装帮助")
    print("=" * 60)
    print(get_ffmpeg_help_message())

print("=" * 60)
print(f"结果: {'✓ 所有检查通过' if all_ok else '✗ 需要安装 FFmpeg'}")
print("=" * 60)

sys.exit(0 if all_ok else 1)
