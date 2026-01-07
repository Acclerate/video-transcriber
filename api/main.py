"""
Video Transcriber Web API
基于FastAPI的Web服务接口
"""

import os
import sys
import asyncio
from typing import Dict, Any
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, BackgroundTasks, WebSocket, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import uvicorn
from loguru import logger
from rich.console import Console

from models.schemas import (
    ProcessOptions,
    APIResponse, TranscribeResponse,
    WhisperModel, Language, OutputFormat
)
from core import transcription_engine
from utils import setup_default_logger, check_ffmpeg_installed, get_ffmpeg_help_message
from .websocket import websocket_endpoint, ws_manager


# 速率限制器
limiter = Limiter(key_func=get_remote_address)

# 用于启动时消息输出的控制台
startup_console = Console(stderr=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("启动Video Transcriber API服务")

    # 初始化日志
    setup_default_logger(
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        log_file=os.getenv("LOG_FILE", "./logs/api.log"),
        log_to_console=True
    )

    # 依赖检查
    if not check_ffmpeg_installed():
        startup_console.print("\n[bold red]╔════════════════════════════════════════════════════════════════╗[/bold red]")
        startup_console.print("[bold red]║                     依赖检查失败                                 ║[/bold red]")
        startup_console.print("[bold red]╚════════════════════════════════════════════════════════════════╝[/bold red]\n")
        startup_console.print(get_ffmpeg_help_message())
        startup_console.print("[bold red]API 服务启动失败: 缺少必需的依赖[/bold red]\n")
        sys.exit(1)
    else:
        logger.info("依赖检查通过: FFmpeg 可用")

    # 启动后台清理任务
    cleanup_task = asyncio.create_task(background_cleanup())

    yield

    # 关闭时执行
    logger.info("关闭Video Transcriber API服务")
    cleanup_task.cancel()

    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


# 创建FastAPI应用
app = FastAPI(
    title="Video Transcriber API",
    description="视频文件转文本服务API",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 添加速率限制中间件
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# CORS配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务
if os.path.exists("web"):
    app.mount("/static", StaticFiles(directory="web"), name="static")


async def background_cleanup():
    """后台清理任务"""
    while True:
        try:
            # 每小时执行一次清理
            await asyncio.sleep(3600)

            # 清理旧任务记录
            transcription_engine.cleanup_old_tasks(24)

            # 清理临时文件
            await transcription_engine.cleanup_temp_files()

            logger.info("后台清理任务完成")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"后台清理任务失败: {e}")


@app.get("/", response_class=HTMLResponse)
async def root():
    """根路径，返回Web界面"""
    if os.path.exists("web/index.html"):
        return FileResponse("web/index.html")
    else:
        return HTMLResponse("""
        <html>
            <head>
                <title>Video Transcriber API</title>
            </head>
            <body>
                <h1>Video Transcriber API</h1>
                <p>视频文件转文本服务API已启动</p>
                <ul>
                    <li><a href="/docs">API文档</a></li>
                    <li><a href="/redoc">ReDoc文档</a></li>
                </ul>
            </body>
        </html>
        """)


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "message": "服务运行正常"}


@app.post("/api/v1/transcribe", response_model=TranscribeResponse)
async def transcribe_upload(
    file: UploadFile = File(...),
    model: str = Form("small"),
    language: str = Form("auto"),
    with_timestamps: bool = Form(False),
    output_format: str = Form("json")
):
    """上传视频文件并转录"""
    temp_file_path = None
    try:
        logger.info(f"收到文件上传请求: {file.filename}")

        # 验证文件类型
        if not file.content_type or not file.content_type.startswith("video/"):
            raise HTTPException(status_code=400, detail="请上传视频文件")

        # 创建上传目录
        upload_dir = Path("./temp/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        # 保存上传的文件
        temp_file_path = upload_dir / file.filename
        with open(temp_file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)

        logger.info(f"文件已保存: {temp_file_path}, 大小: {temp_file_path.stat().st_size} bytes")

        # 构建请求选项
        options = ProcessOptions(
            model=WhisperModel(model),
            language=Language(language),
            with_timestamps=with_timestamps,
            output_format=OutputFormat(output_format),
            enable_gpu=True,
            temperature=0.0
        )

        # 执行转录
        result = await transcription_engine.process_video_file(
            file_path=str(temp_file_path),
            options=options
        )

        # 获取视频信息
        video_info = None
        for task_info in transcription_engine.tasks.values():
            if task_info.file_path == str(temp_file_path) and task_info.video_info:
                video_info = task_info.video_info.model_dump()
                break

        # 返回结果
        response_data = {
            "video_info": video_info,
            "transcription": result.model_dump()
        }

        return TranscribeResponse(
            code=200,
            message="转录成功",
            data=response_data
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"转录失败: {e}")
        raise HTTPException(status_code=500, detail=f"转录失败: {str(e)}")
    finally:
        # 清理上传的文件
        if temp_file_path and temp_file_path.exists():
            try:
                temp_file_path.unlink()
                logger.debug(f"已清理临时文件: {temp_file_path}")
            except Exception as e:
                logger.warning(f"清理临时文件失败: {e}")


@app.post("/api/v1/batch-transcribe")
async def batch_transcribe_videos(
    files: list[UploadFile] = File(...),
    model: str = Form("small"),
    language: str = Form("auto"),
    max_concurrent: int = Form(3)
):
    """批量转录视频文件"""
    try:
        logger.info(f"收到批量转录请求: {len(files)} 个文件")

        # 验证文件数量
        if len(files) > 10:
            raise HTTPException(status_code=400, detail="单次最多支持10个文件")

        # 验证所有文件类型
        for file in files:
            if not file.content_type or not file.content_type.startswith("video/"):
                raise HTTPException(status_code=400, detail=f"请上传视频文件: {file.filename}")

        # 保存上传的文件
        upload_dir = Path("./temp/uploads")
        upload_dir.mkdir(parents=True, exist_ok=True)

        file_paths = []
        temp_files = []

        for file in files:
            temp_file_path = upload_dir / file.filename
            with open(temp_file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
            file_paths.append(str(temp_file_path))
            temp_files.append(temp_file_path)

        # 设置选项
        options = ProcessOptions(
            model=WhisperModel(model),
            language=Language(language),
            with_timestamps=False,
            output_format=OutputFormat.TXT,
            enable_gpu=True,
            temperature=0.0
        )

        # 启动批量处理（异步）
        async def process_batch():
            try:
                await transcription_engine.process_batch_files(
                    file_paths=file_paths,
                    options=options,
                    max_concurrent=max_concurrent
                )
            finally:
                # 清理上传的文件
                for temp_file in temp_files:
                    try:
                        if temp_file.exists():
                            temp_file.unlink()
                    except Exception:
                        pass

        asyncio.create_task(process_batch())

        # 创建批量任务记录
        batch_id = transcription_engine._generate_batch_id()

        return APIResponse(
            code=200,
            message="批量任务已创建",
            data={
                "batch_id": batch_id,
                "total_files": len(files),
                "status": "processing"
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量转录失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量转录失败: {str(e)}")


@app.get("/api/v1/status/{task_id}")
async def get_task_status(task_id: str):
    """查询任务状态"""
    try:
        from models.schemas import TaskStatusResponse

        task_info = transcription_engine.get_task_status(task_id)

        if not task_info:
            raise HTTPException(status_code=404, detail="任务不存在")

        return TaskStatusResponse(
            code=200,
            message="查询成功",
            data=task_info
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询任务状态失败: {e}")
        raise HTTPException(status_code=500, detail="查询失败")


@app.get("/api/v1/batch-status/{batch_id}")
async def get_batch_status(batch_id: str):
    """查询批量任务状态"""
    try:
        batch_info = transcription_engine.get_batch_status(batch_id)

        if not batch_info:
            raise HTTPException(status_code=404, detail="批量任务不存在")

        return APIResponse(
            code=200,
            message="查询成功",
            data=batch_info.model_dump()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"查询批量任务状态失败: {e}")
        raise HTTPException(status_code=500, detail="查询失败")


@app.get("/api/v1/models")
async def get_available_models():
    """获取可用的Whisper模型"""
    try:
        from core.transcriber import speech_transcriber

        models_info = speech_transcriber.get_available_models()
        current_model = speech_transcriber.get_model_info()

        return APIResponse(
            code=200,
            message="查询成功",
            data={
                "available_models": models_info,
                "current_model": current_model
            }
        )

    except Exception as e:
        logger.error(f"查询模型信息失败: {e}")
        raise HTTPException(status_code=500, detail="查询失败")


@app.get("/api/v1/stats")
async def get_statistics():
    """获取系统统计信息"""
    try:
        stats = transcription_engine.get_statistics()

        return APIResponse(
            code=200,
            message="查询成功",
            data=stats
        )

    except Exception as e:
        logger.error(f"查询统计信息失败: {e}")
        raise HTTPException(status_code=500, detail="查询失败")


@app.post("/api/v1/cleanup")
async def cleanup_system():
    """清理系统"""
    try:
        # 清理任务记录
        cleaned_tasks = transcription_engine.cleanup_old_tasks(24)

        # 清理临时文件
        cleaned_files = await transcription_engine.cleanup_temp_files()

        return APIResponse(
            code=200,
            message="清理完成",
            data={
                "cleaned_tasks": cleaned_tasks,
                "cleaned_files": cleaned_files
            }
        )

    except Exception as e:
        logger.error(f"系统清理失败: {e}")
        raise HTTPException(status_code=500, detail="清理失败")


@app.websocket("/ws/transcribe")
async def websocket_transcribe(websocket: WebSocket):
    """WebSocket转录端点"""
    await websocket_endpoint(websocket)


@app.get("/api/v1/ws/status")
async def get_websocket_status():
    """获取WebSocket状态"""
    return APIResponse(
        code=200,
        message="查询成功",
        data={
            "active_connections": ws_manager.get_connection_count(),
            "task_subscriptions": len(ws_manager.task_subscriptions)
        }
    )


# 错误处理
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return JSONResponse(
        status_code=404,
        content={
            "code": 404,
            "message": "资源不存在",
            "data": None
        }
    )


@app.exception_handler(500)
async def internal_error_handler(request: Request, exc):
    logger.error(f"内部服务器错误: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "code": 500,
            "message": "内部服务器错误",
            "data": None
        }
    )


if __name__ == "__main__":
    # 直接运行服务
    uvicorn.run(
        "api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8665)),
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level="info"
    )
