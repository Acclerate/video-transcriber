#!/usr/bin/env python3
"""
Video Transcriber - 视频文件转文本工具
主程序入口和命令行界面
"""

import os
import sys
import asyncio
import argparse
from pathlib import Path
from typing import List, Optional

import click
from rich.console import Console
from rich.progress import Progress, TaskID
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from dotenv import load_dotenv

# 添加项目根目录到Python路径
sys.path.insert(0, str(Path(__file__).parent))

from models.schemas import WhisperModel, Language, OutputFormat, ProcessOptions
from config import settings
from services import TranscriptionService
from utils.logging import setup_default_logger
from utils.file import format_duration, format_file_size
from utils.ffmpeg import check_ffmpeg_installed, get_ffmpeg_help_message

# 加载环境变量
load_dotenv()

# 初始化控制台
console = Console()


# ============================================================================
# 依赖检查
# ============================================================================

def check_startup_dependencies(exit_on_error: bool = True) -> bool:
    """
    启动时检查必需的依赖

    Args:
        exit_on_error: 如果依赖缺失是否退出程序

    Returns:
        bool: 依赖是否全部满足
    """
    all_ok = True
    missing = []

    # 检查 FFmpeg
    if not check_ffmpeg_installed():
        all_ok = False
        missing.append("FFmpeg")

    if not all_ok:
        console.print("\n[bold red]╔════════════════════════════════════════════════════════════════╗[/bold red]")
        console.print("[bold red]║                     依赖检查失败                                 ║[/bold red]")
        console.print("[bold red]╚════════════════════════════════════════════════════════════════╝[/bold red]\n")

        for dep in missing:
            if dep == "FFmpeg":
                console.print(get_ffmpeg_help_message())

        console.print("[bold yellow]提示: 安装完成后重新运行此命令[/bold yellow]\n")

        if exit_on_error:
            sys.exit(1)

    return all_ok


class ProgressCallback:
    """进度回调处理器"""

    def __init__(self, progress: Progress, task_id: TaskID):
        self.progress = progress
        self.task_id = task_id

    def __call__(self, task_id: str, progress_value: float, message: str):
        self.progress.update(
            self.task_id,
            completed=progress_value,
            description=f"[cyan]{message}[/cyan]"
        )


def print_banner():
    """打印程序横幅"""
    banner = """
╭─────────────────────────────────────────╮
│          Video Transcriber              │
│         视频文件转文本工具                 │
│                                         │
│    🎥 支持本地视频文件                   │
│    🤖 基于OpenAI Whisper高精度识别         │
│    🔒 本地处理，保护隐私                   │
╰─────────────────────────────────────────╯
"""
    console.print(Panel(banner, style="bright_blue"))


def print_model_info():
    """打印模型信息"""
    table = Table(title="🤖 可用的Whisper模型", show_header=True, header_style="bold magenta")
    table.add_column("模型", style="cyan")
    table.add_column("大小", style="green")
    table.add_column("速度", style="yellow")
    table.add_column("准确率", style="red")
    table.add_column("推荐场景", style="blue")

    model_data = [
        ("tiny", "39MB", "~10x", "★★☆☆☆", "快速预览"),
        ("base", "74MB", "~7x", "★★★☆☆", "一般使用"),
        ("small", "244MB", "~4x", "★★★★☆", "推荐使用"),
        ("medium", "769MB", "~2x", "★★★★★", "高质量需求"),
        ("large", "1550MB", "~1x", "★★★★★", "专业场景")
    ]

    for model, size, speed, accuracy, scene in model_data:
        table.add_row(model, size, speed, accuracy, scene)

    console.print(table)


@click.group()
@click.option('--debug', is_flag=True, help='启用调试模式')
@click.option('--log-level', default='INFO', help='日志级别')
@click.option('--skip-deps-check', is_flag=True, help='跳过依赖检查（不推荐）')
@click.pass_context
def cli(ctx, debug, log_level, skip_deps_check):
    """Video Transcriber - 视频文件转文本工具"""
    ctx.ensure_object(dict)
    ctx.obj['debug'] = debug

    # 设置日志
    if debug:
        log_level = 'DEBUG'

    setup_default_logger(
        log_level=log_level,
        log_to_console=True,
        log_file='./logs/app.log' if not debug else None
    )

    # 依赖检查（除非明确跳过）
    if not skip_deps_check:
        check_startup_dependencies(exit_on_error=True)


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--model', '-m',
              type=click.Choice(['tiny', 'base', 'small', 'medium', 'large']),
              default='small', help='Whisper模型 (默认: small)')
@click.option('--language', '-l',
              type=click.Choice(['auto', 'zh', 'en', 'ja', 'ko', 'es', 'fr', 'de', 'ru']),
              default='auto', help='目标语言 (默认: auto)')
@click.option('--output', '-o', help='输出文件路径')
@click.option('--format', '-f', 'output_format',
              type=click.Choice(['json', 'txt', 'srt', 'vtt']),
              default='txt', help='输出格式 (默认: txt)')
@click.option('--timestamps', is_flag=True, help='包含时间戳')
@click.option('--quiet', '-q', is_flag=True, help='静默模式')
def transcribe(file_path, model, language, output, output_format, timestamps, quiet):
    """转录单个视频文件"""
    asyncio.run(_transcribe_single(file_path, model, language, output, output_format, timestamps, quiet))


async def _transcribe_single(file_path, model, language, output, output_format, timestamps, quiet):
    """异步转录单个视频文件"""
    try:
        if not quiet:
            print_banner()
            console.print(f"[bold green]开始处理视频文件:[/bold green] {file_path}")

        # 验证文件
        file_path_obj = Path(file_path)
        if not file_path_obj.exists():
            console.print("[bold red]错误:[/bold red] 文件不存在")
            sys.exit(1)

        if not file_path_obj.is_file():
            console.print("[bold red]错误:[/bold red] 路径不是文件")
            sys.exit(1)

        # 设置选项
        options = ProcessOptions(
            model=WhisperModel(model),
            language=Language(language),
            with_timestamps=timestamps,
            output_format=OutputFormat(output_format),
            enable_gpu=settings.ENABLE_GPU,
            temperature=settings.DEFAULT_TEMPERATURE
        )

        # 使用服务层
        service = TranscriptionService(settings)

        # 创建进度条
        with Progress() as progress:
            if not quiet:
                task = progress.add_task("[cyan]处理中...", total=100)
                callback = ProgressCallback(progress, task)
            else:
                callback = None

            # 执行转录
            result = await service.transcribe_file(
                file_path=str(file_path_obj.absolute()),
                options=options,
                progress_callback=callback
            )

        # 处理输出
        if output_format == 'json':
            output_text = result.model_dump_json(indent=2)
        else:
            from core.transcriber import speech_transcriber
            output_text = speech_transcriber.format_output(result, OutputFormat(output_format))

        # 保存或显示结果
        if output:
            output_path = Path(output)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(output_text)

            if not quiet:
                console.print(f"[bold green]结果已保存到:[/bold green] {output}")
        else:
            if not quiet:
                console.print("\n[bold yellow]转录结果:[/bold yellow]")
                console.print(Panel(output_text, title="转录内容", border_style="green"))
            else:
                print(output_text)

        if not quiet:
            # 显示统计信息
            stats_table = Table(show_header=False, box=None)
            stats_table.add_row("🎯 置信度:", f"{result.confidence:.1%}")
            stats_table.add_row("🌍 检测语言:", result.language)
            stats_table.add_row("⏱️ 处理时间:", format_duration(result.processing_time))
            stats_table.add_row("🤖 使用模型:", result.whisper_model.value)
            stats_table.add_row("📝 文本长度:", f"{len(result.text)} 字符")

            console.print("\n[bold blue]处理统计:[/bold blue]")
            console.print(stats_table)

    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断处理[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]错误:[/bold red] {e}")
        sys.exit(1)


@cli.command()
@click.argument('file_path', type=click.Path(exists=True))
@click.option('--model', '-m',
              type=click.Choice(['tiny', 'base', 'small', 'medium', 'large']),
              default='small', help='Whisper模型')
@click.option('--language', '-l',
              type=click.Choice(['auto', 'zh', 'en', 'ja', 'ko']),
              default='auto', help='目标语言')
@click.option('--output-dir', '-d', help='输出目录')
@click.option('--format', '-f', 'output_format',
              type=click.Choice(['json', 'txt', 'srt', 'vtt']),
              default='txt', help='输出格式')
@click.option('--max-concurrent', '-c', default=3, help='最大并发数')
@click.option('--quiet', '-q', is_flag=True, help='静默模式')
def batch(file_path, model, language, output_dir, output_format, max_concurrent, quiet):
    """批量转录视频（从文件读取文件路径列表）"""
    asyncio.run(_transcribe_batch(file_path, model, language, output_dir, output_format, max_concurrent, quiet))


async def _transcribe_batch(file_path, model, language, output_dir, output_format, max_concurrent, quiet):
    """异步批量转录"""
    try:
        if not quiet:
            print_banner()

        # 读取文件路径列表
        with open(file_path, 'r', encoding='utf-8') as f:
            paths = [line.strip() for line in f if line.strip() and not line.startswith('#')]

        if not paths:
            console.print("[bold red]错误:[/bold red] 文件中没有找到有效的路径")
            sys.exit(1)

        console.print(f"[bold green]找到 {len(paths)} 个文件路径[/bold green]")

        # 验证文件路径
        valid_paths = []
        for path in paths:
            if Path(path).exists() and Path(path).is_file():
                valid_paths.append(path)
            else:
                console.print(f"[yellow]跳过无效路径:[/yellow] {path}")

        if not valid_paths:
            console.print("[bold red]错误:[/bold red] 没有有效的文件路径")
            sys.exit(1)

        # 设置选项
        options = ProcessOptions(
            model=WhisperModel(model),
            language=Language(language),
            with_timestamps=False,
            output_format=OutputFormat(output_format),
            enable_gpu=True,
            temperature=0.0
        )

        # 设置输出目录
        if output_dir:
            output_path = Path(output_dir)
            output_path.mkdir(parents=True, exist_ok=True)
        else:
            output_path = Path('./output')
            output_path.mkdir(parents=True, exist_ok=True)

        # 执行批量处理
        console.print(f"[bold blue]开始批量处理 {len(valid_paths)} 个视频文件...[/bold blue]")

        # 使用服务层
        service = TranscriptionService(settings)

        def batch_progress(batch_id: str, status_info: dict):
            if not quiet:
                completed = status_info.get('success', 0)
                failed = status_info.get('failed', 0)
                total = status_info.get('total', 0)
                console.print(f"进度: {completed + failed}/{total} (成功: {completed}, 失败: {failed})")

        batch_info = await service.transcribe_batch(
            file_paths=valid_paths,
            options=options,
            max_concurrent=max_concurrent,
            progress_callback=batch_progress
        )

        # 保存结果
        success_count = batch_info.get('success', 0)
        task_service = service.task_service

        for task_id, task_info in task_service.tasks.items():
            if task_info.result:
                # 生成输出文件名
                safe_title = task_info.video_info.file_name if task_info.video_info else "unknown"
                safe_title = "".join(c for c in safe_title if c.isalnum() or c in (' ', '-', '_')).strip()

                output_file = output_path / f"{safe_title}_{task_info.task_id[-8:]}.{output_format}"

                # 格式化输出
                if output_format == 'json':
                    output_text = task_info.result.model_dump_json(indent=2)
                else:
                    from core.transcriber import speech_transcriber
                    output_text = speech_transcriber.format_output(task_info.result, OutputFormat(output_format))

                # 保存文件
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(output_text)

        # 显示结果统计
        console.print(f"\n[bold green]批量处理完成![/bold green]")
        console.print(f"总计: {len(valid_paths)} 个")
        console.print(f"成功: {success_count} 个")
        console.print(f"失败: {len(valid_paths) - success_count} 个")
        console.print(f"输出目录: {output_path}")

    except KeyboardInterrupt:
        console.print("\n[yellow]用户中断处理[/yellow]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[bold red]错误:[/bold red] {e}")
        sys.exit(1)


@cli.command()
def models():
    """显示可用的Whisper模型信息"""
    print_banner()
    print_model_info()


@cli.command()
def info():
    """显示系统信息"""
    print_banner()

    # 系统信息
    import torch
    from core.transcriber import speech_transcriber

    info_table = Table(title="🔧 系统信息", show_header=False)
    info_table.add_row("Python版本:", sys.version.split()[0])
    info_table.add_row("PyTorch版本:", torch.__version__)
    info_table.add_row("CUDA可用:", "是" if torch.cuda.is_available() else "否")

    if torch.cuda.is_available():
        info_table.add_row("CUDA设备:", torch.cuda.get_device_name(0))
        info_table.add_row("CUDA内存:", f"{torch.cuda.get_device_properties(0).total_memory // 1024**3}GB")

    info_table.add_row("当前模型:", speech_transcriber.model_name.value)
    info_table.add_row("模型设备:", speech_transcriber.device)

    console.print(info_table)

    # 统计信息 - 使用服务层
    service = TranscriptionService(settings)
    stats = service.get_statistics()
    stats_table = Table(title="📊 使用统计", show_header=False)
    stats_table.add_row("总处理数:", str(stats['total_processed']))
    stats_table.add_row("成功数:", str(stats['total_success']))
    stats_table.add_row("失败数:", str(stats['total_failed']))
    stats_table.add_row("活跃任务:", str(stats['active_tasks']))
    stats_table.add_row("平均处理时间:", format_duration(stats['average_processing_time']))

    console.print(stats_table)


@cli.command()
@click.option('--hours', default=24, help='清理多少小时前的文件')
def cleanup(hours):
    """清理临时文件和旧任务记录"""
    try:
        console.print("[bold blue]开始清理...[/bold blue]")

        # 使用服务层
        service = TranscriptionService(settings)

        # 清理任务记录
        cleaned_tasks = service.task_service.cleanup_old_tasks(hours)
        console.print(f"清理任务记录: {cleaned_tasks} 个")

        # 清理临时文件
        cleaned_files = asyncio.run(service.cleanup_temp_files())
        console.print(f"清理临时文件: {cleaned_files} 个")

        console.print("[bold green]清理完成![/bold green]")

    except Exception as e:
        console.print(f"[bold red]清理失败:[/bold red] {e}")


@cli.command()
def check():
    """检查系统依赖是否满足要求"""
    from utils import get_ffmpeg_version, print_dependency_check

    console.print("\n[bold cyan]╔════════════════════════════════════════════════════════════════╗[/bold cyan]")
    console.print("[bold cyan]║                      系统依赖检查                               ║[/bold cyan]")
    console.print("[bold cyan]╚════════════════════════════════════════════════════════════════╝[/bold cyan]\n")

    all_ok = print_dependency_check(console)

    if all_ok:
        # 显示 FFmpeg 版本信息
        ffmpeg_version = get_ffmpeg_version()
        if ffmpeg_version:
            console.print(f"\n[bold green]✓ FFmpeg 版本信息:[/bold green]")
            console.print(f"  {ffmpeg_version.split()[0]} {ffmpeg_version.split()[2]}")
            # 显示更多版本信息
            lines = ffmpeg_version.split('\n')
            for line in lines[1:4]:  # 显示前几行配置信息
                if line.strip():
                    console.print(f"  {line.strip()}")

        console.print("\n[bold green]✓ 所有依赖已满足，可以正常使用![/bold green]\n")
    else:
        console.print("\n[bold yellow]请按照上述提示安装缺失的依赖[/bold yellow]\n")
        sys.exit(1)


@cli.command()
@click.option('--host', default='0.0.0.0', help='服务主机')
@click.option('--port', default=8665, help='服务端口')
@click.option('--reload', is_flag=True, help='自动重载')
def serve(host, port, reload):
    """启动Web API服务"""
    try:
        import uvicorn
        console.print(f"[bold blue]启动Web服务...[/bold blue]")
        console.print(f"地址: http://{host}:{port}")
        console.print(f"文档: http://{host}:{port}/docs")

        uvicorn.run(
            "api.main:app",
            host=host,
            port=port,
            reload=reload,
            log_level="info"
        )
    except ImportError:
        console.print("[bold red]错误:[/bold red] 需要安装uvicorn才能启动Web服务")
        console.print("请运行: pip install uvicorn")
    except Exception as e:
        console.print(f"[bold red]服务启动失败:[/bold red] {e}")


if __name__ == "__main__":
    try:
        cli()
    except KeyboardInterrupt:
        console.print("\n[yellow]程序已退出[/yellow]")
    except Exception as e:
        console.print(f"[bold red]程序错误:[/bold red] {e}")
        sys.exit(1)
