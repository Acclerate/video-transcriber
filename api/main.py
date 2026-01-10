"""
Video Transcriber Web API
基于FastAPI的Web服务接口
"""

import os
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket
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

from config import settings
from models.schemas import APIResponse
from utils.logging import setup_default_logger
from utils.ffmpeg import check_ffmpeg_installed, get_ffmpeg_help_message
from .routes import health_router, transcribe_router
from .websocket import websocket_endpoint, ws_manager

# 导入核心引擎
from core.engine import transcription_engine


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
        log_level=settings.LOG_LEVEL,
        log_file=str(settings.log_file_path),
        log_to_console=settings.LOG_TO_CONSOLE
    )

    # 依赖检查
    if not check_ffmpeg_installed():
        startup_console.print("\n[bold red]╔════════════════════════════════════════════════════════════════╗[/bold red]")
        startup_console.print("[bold red]║                     依赖检查失败                                 ║[/bold red]")
        startup_console.print("[bold red]╚════════════════════════════════════════════════════════════════╝[/bold red]\n")
        startup_console.print(get_ffmpeg_help_message())
        startup_console.print("[bold red]API 服务启动失败: 缺少必需的依赖[/bold red]\n")
        import sys
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
    title=settings.APP_NAME,
    description="视频文件转文本服务API",
    version=settings.APP_VERSION,
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
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# 注册路由
app.include_router(health_router)
app.include_router(transcribe_router)

# 静态文件服务
if os.path.exists("web"):
    app.mount("/static", StaticFiles(directory="web"), name="static")


async def background_cleanup():
    """后台清理任务"""
    from services import TranscriptionService
    service = TranscriptionService(settings)
    while True:
        try:
            # 每小时执行一次清理
            await asyncio.sleep(settings.TASK_CLEANUP_INTERVAL)

            # 清理旧任务记录
            await service.cleanup_old_tasks(settings.TASK_RETENTION_HOURS)

            # 清理临时文件
            await service.cleanup_temp_files()

            logger.info("后台清理任务完成")

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"后台清理任务失败: {e}")


# ============================================================
# 根路径端点
# ============================================================

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


# ============================================================
# 任务状态查询端点 (transcribe_router 中没有的)
# ============================================================

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


# ============================================================
# 模型和系统信息端点
# ============================================================

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


# ============================================================
# WebSocket 端点
# ============================================================

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


# ============================================================
# 错误处理
# ============================================================

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


# ============================================================
# 直接运行支持
# ============================================================

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app",
        host=os.getenv("HOST", "0.0.0.0"),
        port=int(os.getenv("PORT", 8665)),
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level="info"
    )
