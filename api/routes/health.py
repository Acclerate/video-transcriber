"""
健康检查路由
提供服务健康状态检查端点
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from config import settings
from utils.ffmpeg import check_ffmpeg_installed, get_ffmpeg_version


health_router = APIRouter(tags=["健康检查"])


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str = Field(..., description="服务状态")
    version: str = Field(..., description="应用版本")
    environment: str = Field(..., description="运行环境")
    components: dict = Field(default_factory=dict, description="组件状态")


class ComponentStatus(BaseModel):
    """组件状态"""
    healthy: bool = Field(..., description="是否健康")
    version: str | None = Field(None, description="组件版本")
    message: str = Field(..., description="状态消息")


@health_router.get("/health", response_model=HealthResponse)
async def health_check():
    """
    健康检查端点

    检查服务及其依赖组件的健康状态

    Returns:
        HealthResponse: 健康状态信息
    """
    components = {}

    # 检查 FFmpeg
    ffmpeg_installed = check_ffmpeg_installed()
    if ffmpeg_installed:
        ffmpeg_version = get_ffmpeg_version()
        if ffmpeg_version:
            version = ffmpeg_version.split()[2] if len(ffmpeg_version.split()) > 2 else "unknown"
            components["ffmpeg"] = ComponentStatus(
                healthy=True,
                version=version,
                message="FFmpeg 可用"
            )
        else:
            components["ffmpeg"] = ComponentStatus(
                healthy=True,
                version=None,
                message="FFmpeg 可用但无法获取版本"
            )
    else:
        components["ffmpeg"] = ComponentStatus(
            healthy=False,
            version=None,
            message="FFmpeg 未安装"
        )

    # 检查整体状态
    all_healthy = all(c.healthy for c in components.values())
    status = "healthy" if all_healthy else "degraded"

    return HealthResponse(
        status=status,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        components=components
    )


@health_router.get("/ping")
async def ping():
    """
    简单的 ping 端点

    用于测试服务是否响应

    Returns:
        dict: pong 响应
    """
    return {"ping": "pong"}


@health_router.get("/info")
async def service_info():
    """
    服务信息端点

    返回服务的详细信息

    Returns:
        dict: 服务信息
    """
    return {
        "name": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
        "debug": settings.DEBUG,
        "features": {
            "gpu_support": settings.ENABLE_GPU,
            "platform_download": settings.ENABLE_PLATFORM_DOWNLOAD,
            "batch_processing": True,
            "websocket": True,
        },
        "limits": {
            "max_file_size_mb": settings.MAX_FILE_SIZE,
            "max_concurrent_tasks": settings.MAX_CONCURRENT_TASKS,
            "rate_limit_per_minute": settings.RATE_LIMIT_PER_MINUTE,
        },
        "supported_formats": {
            "video": settings.VIDEO_FORMATS,
            "audio": settings.AUDIO_FORMATS,
        },
        "models": {
            "default": settings.DEFAULT_MODEL,
            "available": ["tiny", "base", "small", "medium", "large"],
        }
    }
