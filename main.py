#!/usr/bin/env python3
"""
Video Transcriber - 短视频转文本工具
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
from core import transcription_engine, transcribe_video_url
from utils import setup_default_logger, format_duration, format_file_size, validate_url

# 加载环境变量
load_dotenv()

# 初始化控制台
console = Console()


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
│         短视频转文本工具                   │
│                                         │
│    🎥 支持抖音、B站等主流平台              │
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
@click.pass_context
def cli(ctx, debug, log_level):
    """Video Transcriber - 短视频转文本工具"""
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


@cli.command()
@click.argument('url')
@click.option('--model', '-m', 
              type=click.Choice(['tiny', 'base', 'small', 'medium', 'large']), 
              default='small', help='Whisper模型 (默认: small)')
@click.option('--language', '-l', 
              type=click.Choice(['auto', 'zh', 'en', 'ja', 'ko']), 
              default='auto', help='目标语言 (默认: auto)')
@click.option('--output', '-o', help='输出文件路径')
@click.option('--format', '-f', 'output_format',
              type=click.Choice(['json', 'txt', 'srt', 'vtt']), 
              default='txt', help='输出格式 (默认: txt)')
@click.option('--timestamps', is_flag=True, help='包含时间戳')
@click.option('--quiet', '-q', is_flag=True, help='静默模式')
def transcribe(url, model, language, output, output_format, timestamps, quiet):
    """转录单个视频"""
    asyncio.run(_transcribe_single(url, model, language, output, output_format, timestamps, quiet))


async def _transcribe_single(url, model, language, output, output_format, timestamps, quiet):
    """异步转录单个视频"""
    try:
        if not quiet:
            print_banner()
            console.print(f"[bold green]开始处理视频:[/bold green] {url}")
        
        # 验证URL
        if not validate_url(url):
            console.print("[bold red]错误:[/bold red] 无效的视频链接")
            sys.exit(1)
        
        # 设置选项
        options = ProcessOptions(
                    model=WhisperModel(model),
                    language=Language(language),
                    with_timestamps=timestamps,
                    output_format=OutputFormat(output_format),
                    enable_gpu=True,
                    temperature=0.0
                )
        
        # 创建进度条
        with Progress() as progress:
            if not quiet:
                task = progress.add_task("[cyan]处理中...", total=100)
                callback = ProgressCallback(progress, task)
            else:
                callback = None
            
            # 执行转录
            result = await transcription_engine.process_video_url(
                url=url,
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
    """批量转录视频（从文件读取URL列表）"""
    asyncio.run(_transcribe_batch(file_path, model, language, output_dir, output_format, max_concurrent, quiet))


async def _transcribe_batch(file_path, model, language, output_dir, output_format, max_concurrent, quiet):
    """异步批量转录"""
    try:
        if not quiet:
            print_banner()
        
        # 读取URL列表
        with open(file_path, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip() and not line.startswith('#')]
        
        if not urls:
            console.print("[bold red]错误:[/bold red] 文件中没有找到有效的URL")
            sys.exit(1)
        
        console.print(f"[bold green]找到 {len(urls)} 个视频链接[/bold green]")
        
        # 验证URLs
        valid_urls = []
        for url in urls:
            if validate_url(url):
                valid_urls.append(url)
            else:
                console.print(f"[yellow]跳过无效URL:[/yellow] {url}")
        
        if not valid_urls:
            console.print("[bold red]错误:[/bold red] 没有有效的URL")
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
        console.print(f"[bold blue]开始批量处理 {len(valid_urls)} 个视频...[/bold blue]")
        
        def batch_progress(batch_id: str, status_info: dict):
            if not quiet:
                completed = status_info.get('completed', 0)
                failed = status_info.get('failed', 0)
                total = status_info.get('total', 0)
                console.print(f"进度: {completed + failed}/{total} (成功: {completed}, 失败: {failed})")
        
        batch_info = await transcription_engine.process_batch_urls(
            urls=valid_urls,
            options=options,
            max_concurrent=max_concurrent,
            progress_callback=batch_progress
        )
        
        # 保存结果
        success_count = 0
        for task_id, task_info in transcription_engine.tasks.items():
            if task_info.result:
                # 生成输出文件名
                safe_title = task_info.video_info.title if task_info.video_info else "unknown"
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
                
                success_count += 1
        
        # 显示结果统计
        console.print(f"\n[bold green]批量处理完成![/bold green]")
        console.print(f"总计: {len(valid_urls)} 个")
        console.print(f"成功: {success_count} 个")
        console.print(f"失败: {len(valid_urls) - success_count} 个")
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
    
    # 统计信息
    stats = transcription_engine.get_statistics()
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
        
        # 清理任务记录
        cleaned_tasks = transcription_engine.cleanup_old_tasks(hours)
        console.print(f"清理任务记录: {cleaned_tasks} 个")
        
        # 清理临时文件
        cleaned_files = asyncio.run(transcription_engine.cleanup_temp_files())
        console.print(f"清理临时文件: {cleaned_files} 个")
        
        console.print("[bold green]清理完成![/bold green]")
    
    except Exception as e:
        console.print(f"[bold red]清理失败:[/bold red] {e}")


@cli.command()
@click.option('--host', default='0.0.0.0', help='服务主机')
@click.option('--port', default=8000, help='服务端口')
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