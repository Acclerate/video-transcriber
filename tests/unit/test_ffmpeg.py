#!/usr/bin/env python3
"""
测试 FFmpeg 检测功能
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from rich.console import Console
from utils.helpers import (
    check_ffmpeg_installed,
    get_ffmpeg_version,
    get_ffmpeg_install_command,
    get_ffmpeg_help_message,
    check_dependencies,
    print_dependency_check
)

def test_ffmpeg_detection():
    """测试 FFmpeg 检测功能"""
    console = Console()

    console.print("\n[bold cyan]╔════════════════════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║                  FFmpeg 检测功能测试                              ║[/bold cyan]")
    console.print("[bold cyan]╚════════════════════════════════════════════════════════════════╝[/bold cyan]\n")

    # 测试 1: 检查 FFmpeg 是否安装
    console.print("[bold yellow]测试 1: 检查 FFmpeg 是否安装[/bold yellow]")
    is_installed = check_ffmpeg_installed()
    console.print(f"  结果: {'[green]✓ 已安装[/green]' if is_installed else '[red]✗ 未安装[/red]'}\n")

    # 测试 2: 获取 FFmpeg 版本
    console.print("[bold yellow]测试 2: 获取 FFmpeg 版本信息[/bold yellow]")
    version = get_ffmpeg_version()
    if version:
        console.print(f"  [green]✓[/green] {version.split()[0]} {version.split()[2] if len(version.split()) > 2 else ''}")
    else:
        console.print(f"  [red]✗ 无法获取版本信息[/red]")
    console.print()

    # 测试 3: 获取安装命令
    console.print("[bold yellow]测试 3: 获取当前系统的安装命令[/bold yellow]")
    install_cmd = get_ffmpeg_install_command()
    console.print(f"  命令:\n[dim]{install_cmd}[/dim]\n")

    # 测试 4: 依赖检查
    console.print("[bold yellow]测试 4: 运行完整依赖检查[/bold yellow]")
    all_ok, missing = check_dependencies()
    console.print(f"  结果: {'[green]✓ 所有依赖满足[/green]' if all_ok else f'[red]✗ 缺失依赖: {missing}[/red]'}\n")

    # 测试 5: 打印检查结果
    console.print("[bold yellow]测试 5: 使用 Rich 格式化输出[/bold yellow]")
    console.print()
    print_dependency_check(console)
    console.print()

    # 测试 6: 显示完整帮助信息（如果 FFmpeg 未安装）
    if not is_installed:
        console.print("[bold yellow]测试 6: 显示完整帮助信息[/bold yellow]")
        console.print()
        console.print(get_ffmpeg_help_message())

    # 总结
    console.print("\n[bold cyan]════════════════════════════════════════════════════════════════[/bold cyan]")
    console.print("[bold cyan]                         测试完成                                    [/bold cyan]")
    console.print("[bold cyan]════════════════════════════════════════════════════════════════[/bold cyan]\n")

    return 0 if all_ok else 1


if __name__ == "__main__":
    exit_code = test_ffmpeg_detection()
    sys.exit(exit_code)
