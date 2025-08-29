"""
Video Transcriber Web API
基于FastAPI的Web服务接口
"""

import os
import asyncio
from typing import Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, BackgroundTasks, Depends, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi import Request
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
import uvicorn
from loguru import logger

from models.schemas import (
    TranscribeRequest, BatchTranscribeRequest, ProcessOptions,
    APIResponse, TranscribeResponse, BatchTranscribeResponse,
    TaskStatusResponse, PlatformsResponse, PlatformInfo,
    WhisperModel, Language, Platform, BatchTaskInfo
)
from core import transcription_engine, video_parser
from core.douyin_auth import get_authenticator, cleanup_authenticator, LoginStatus
from core.cookie_manager import get_cookie_manager, validate_cookies, get_cookies_info
from utils import setup_default_logger, validate_url
from .websocket import websocket_endpoint, ws_manager


# 速率限制器
limiter = Limiter(key_func=get_remote_address)

# 认证方案（可选）
security = HTTPBearer(auto_error=False)


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
    
    # 预热Whisper模型（可选）
    try:
        from core.transcriber import speech_transcriber
        await speech_transcriber.load_model()
        logger.info("Whisper模型预加载完成")
    except Exception as e:
        logger.warning(f"模型预加载失败: {e}")
    
    # 启动后台清理任务
    cleanup_task = asyncio.create_task(background_cleanup())
    
    yield
    
    # 关闭时执行
    logger.info("关闭Video Transcriber API服务")
    cleanup_task.cancel()
    
    # 清理抖音认证器
    try:
        await cleanup_authenticator()
    except Exception as e:
        logger.error(f"清理认证器失败: {e}")
    
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


# 创建FastAPI应用
app = FastAPI(
    title="Video Transcriber API",
    description="短视频转文本服务API",
    version="1.0.0",
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


async def verify_api_key(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """验证API密钥（可选）"""
    api_key = os.getenv("API_KEY")
    if api_key and (not credentials or credentials.credentials != api_key):
        raise HTTPException(status_code=401, detail="无效的API密钥")
    return credentials


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
                <p>短视频转文本服务API已启动</p>
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
# @limiter.limit("10/minute")
async def transcribe_video(
    req: Request,
    request: TranscribeRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key)
):
    """转录单个视频"""
    try:
        logger.info(f"收到转录请求: {request.url}")
        
        # 验证URL
        if not validate_url(str(request.url)):
            raise HTTPException(status_code=400, detail="无效的视频链接")
        
        # 执行转录
        result = await transcription_engine.process_video_url(
            url=str(request.url),
            options=request.options
        )
        
        # 获取视频信息
        video_info = None
        for task_info in transcription_engine.tasks.values():
            if str(task_info.url) == str(request.url) and task_info.video_info:
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


@app.post("/api/v1/batch-transcribe", response_model=BatchTranscribeResponse)
# @limiter.limit("3/minute")
async def batch_transcribe_videos(
    req: Request,
    request: BatchTranscribeRequest,
    background_tasks: BackgroundTasks,
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key)
):
    """批量转录视频"""
    try:
        logger.info(f"收到批量转录请求: {len(request.urls)} 个URL")
        
        # 验证URL数量
        if len(request.urls) > 20:
            raise HTTPException(status_code=400, detail="单次最多支持20个视频")
        
        # 验证所有URL
        invalid_urls = []
        for url in request.urls:
            if not validate_url(str(url)):
                invalid_urls.append(str(url))
        
        if invalid_urls:
            raise HTTPException(
                status_code=400, 
                detail=f"存在无效的视频链接: {', '.join(invalid_urls[:3])}"
            )
        
        # 启动批量处理（异步）
        urls_str = [str(url) for url in request.urls]
        
        async def process_batch():
            try:
                await transcription_engine.process_batch_urls(
                    urls=urls_str,
                    options=request.options,
                    max_concurrent=request.max_concurrent
                )
            except Exception as e:
                logger.error(f"批量处理失败: {e}")
        
        background_tasks.add_task(process_batch)
        
        # 创建批量任务记录
        batch_id = transcription_engine._generate_batch_id()
        batch_info = BatchTaskInfo(
            batch_id=batch_id,
            total_count=len(request.urls),
            pending_count=len(request.urls),
            completed_count=0,
            failed_count=0
        )
        
        return BatchTranscribeResponse(
            code=200,
            message="批量任务已创建",
            data=batch_info
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"批量转录失败: {e}")
        raise HTTPException(status_code=500, detail=f"批量转录失败: {str(e)}")


@app.get("/api/v1/status/{task_id}", response_model=TaskStatusResponse)
async def get_task_status(task_id: str):
    """查询任务状态"""
    try:
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


@app.get("/api/v1/platforms", response_model=PlatformsResponse)
async def get_supported_platforms():
    """获取支持的平台列表"""
    try:
        platforms_data = video_parser.get_supported_platforms()
        
        platforms = []
        for platform_name, platform_data in platforms_data.items():
            platforms.append(PlatformInfo(
                name=Platform(platform_name),
                display_name=platform_data["display_name"],
                domains=platform_data["domains"],
                supported=platform_data["supported"]
            ))
        
        return PlatformsResponse(
            code=200,
            message="查询成功",
            data={"platforms": platforms}
        )
        
    except Exception as e:
        logger.error(f"查询支持平台失败: {e}")
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
async def cleanup_system(
    credentials: HTTPAuthorizationCredentials = Depends(verify_api_key)
):
    """清理系统（需要认证）"""
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


@app.websocket("/ws/auth/douyin")
async def websocket_douyin_auth(websocket: WebSocket):
    """WebSocket抖音扫码登录端点"""
    await websocket.accept()
    auth = None
    
    try:
        # 创建认证器实例
        auth = await get_authenticator()
        
        # 添加状态变化回调
        async def status_callback(status: LoginStatus):
            await websocket.send_json({
                "type": "status_change",
                "status": status.value,
                "message": {
                    LoginStatus.INITIALIZING: "正在初始化浏览器...",
                    LoginStatus.QR_GENERATED: "二维码已生成",
                    LoginStatus.WAITING_SCAN: "请使用抖音APP扫描二维码",
                    LoginStatus.SCANNED: "扫描成功，请在手机上确认登录",
                    LoginStatus.SUCCESS: "登录成功！Cookies已保存",
                    LoginStatus.FAILED: "登录失败，请重试",
                    LoginStatus.TIMEOUT: "登录超时，请重新扫码",
                    LoginStatus.STOPPED: "已停止登录流程"
                }.get(status, "未知状态")
            })
        
        auth.add_callback('status_change', status_callback)
        
        # 启动登录流程
        result = await auth.start_login()
        
        # 发送结果
        await websocket.send_json({
            "type": "login_result",
            "status": result.status.value,
            "message": result.message,
            "qr_code": result.qr_code.image_data if result.qr_code else None,
            "cookies_count": len(result.cookies) if result.cookies else 0
        })
        
        # 保持连接，等待客户端断开
        while True:
            try:
                message = await websocket.receive_json()
                if message.get("action") == "refresh_qr":
                    # 刷新二维码
                    qr_code = await auth.refresh_qr_code()
                    if qr_code:
                        await websocket.send_json({
                            "type": "qr_refresh",
                            "qr_code": qr_code.image_data
                        })
                elif message.get("action") == "stop":
                    break
            except Exception:
                break
                
    except Exception as e:
        logger.error(f"WebSocket抖音认证失败: {e}")
        await websocket.send_json({
            "type": "error",
            "message": f"认证失败: {str(e)}"
        })
    finally:
        if auth:
            await auth.stop()
        try:
            await websocket.close()
        except:
            pass


@app.post("/api/v1/auth/douyin/start")
async def start_douyin_auth():
    """启动抖音扫码登录"""
    try:
        auth = await get_authenticator()
        
        # 检查是否已有进行中的认证
        if auth.status not in [LoginStatus.IDLE, LoginStatus.STOPPED, LoginStatus.FAILED]:
            return APIResponse(
                code=400,
                message="已有进行中的登录流程",
                data={"status": auth.status.value}
            )
        
        return APIResponse(
            code=200,
            message="请通过WebSocket连接进行扫码登录",
            data={"websocket_url": "/ws/auth/douyin"}
        )
        
    except Exception as e:
        logger.error(f"启动抖音认证失败: {e}")
        raise HTTPException(status_code=500, detail=f"启动失败: {str(e)}")


@app.get("/api/v1/auth/douyin/status")
async def get_douyin_auth_status():
    """获取抖音登录状态"""
    try:
        auth = await get_authenticator()
        
        return APIResponse(
            code=200,
            message="查询成功",
            data={
                "status": auth.status.value,
                "cookies_exists": auth.cookies_file.exists() if hasattr(auth, 'cookies_file') else False
            }
        )
        
    except Exception as e:
        logger.error(f"查询抖音认证状态失败: {e}")
        raise HTTPException(status_code=500, detail="查询失败")


@app.post("/api/v1/auth/douyin/stop")
async def stop_douyin_auth():
    """停止抖音扫码登录"""
    try:
        await cleanup_authenticator()
        
        return APIResponse(
            code=200,
            message="已停止登录流程",
            data=None
        )
        
    except Exception as e:
        logger.error(f"停止抖音认证失败: {e}")
        raise HTTPException(status_code=500, detail="停止失败")


@app.get("/api/v1/cookies/info")
async def get_cookies_info_api():
    """获取cookies信息"""
    try:
        info = get_cookies_info()
        
        return APIResponse(
            code=200,
            message="查询成功",
            data=info
        )
        
    except Exception as e:
        logger.error(f"获取cookies信息失败: {e}")
        raise HTTPException(status_code=500, detail="查询失败")


@app.get("/api/v1/cookies/validate")
async def validate_cookies_api():
    """验证cookies有效性"""
    try:
        is_valid = validate_cookies()
        
        return APIResponse(
            code=200,
            message="验证完成",
            data={
                "valid": is_valid,
                "message": "Cookies有效" if is_valid else "Cookies无效或不存在"
            }
        )
        
    except Exception as e:
        logger.error(f"验证cookies失败: {e}")
        raise HTTPException(status_code=500, detail="验证失败")


@app.post("/api/v1/cookies/backup")
async def backup_cookies_api():
    """备份cookies"""
    try:
        manager = get_cookie_manager()
        success = manager.backup_cookies()
        
        if success:
            return APIResponse(
                code=200,
                message="Cookies备份成功",
                data=None
            )
        else:
            return APIResponse(
                code=400,
                message="Cookies备份失败",
                data=None
            )
        
    except Exception as e:
        logger.error(f"备份cookies失败: {e}")
        raise HTTPException(status_code=500, detail="备份失败")


@app.get("/api/v1/cookies/backups")
async def get_cookies_backups():
    """获取cookies备份列表"""
    try:
        manager = get_cookie_manager()
        backups = manager.get_backup_list()
        
        return APIResponse(
            code=200,
            message="查询成功",
            data={"backups": backups}
        )
        
    except Exception as e:
        logger.error(f"获取cookies备份列表失败: {e}")
        raise HTTPException(status_code=500, detail="查询失败")


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
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level="info"
    )