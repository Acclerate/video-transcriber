"""
转录路由
处理视频转录相关的 API 端点
"""

from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from loguru import logger

from config import settings
from models.schemas import (
    ProcessOptions, APIResponse, TranscribeResponse,
    TranscriptionResult, WhisperModel, Language, OutputFormat
)
from services import TranscriptionService, FileService

# 速率限制器
limiter = Limiter(key_func=get_remote_address)

# 创建路由器
transcribe_router = APIRouter(
    prefix="/api/v1/transcribe",
    tags=["转录服务"]
)


# 依赖注入
def get_transcription_service() -> TranscriptionService:
    """获取转录服务实例"""
    # 这里可以实现单例模式或使用依赖注入框架
    return TranscriptionService()


def get_file_service() -> FileService:
    """获取文件服务实例"""
    return FileService()


# ============================================================
# 转录端点
# ============================================================

@transcribe_router.post("/file", response_model=TranscribeResponse)
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def transcribe_file(
    file: UploadFile = File(...),
    model: str = Form(default=settings.DEFAULT_MODEL),
    language: str = Form(default="auto"),
    format: str = Form(default="txt"),
    timestamps: bool = Form(default=False),
    background_tasks: BackgroundTasks = None,
    service: TranscriptionService = Depends(get_transcription_service),
    file_service: FileService = Depends(get_file_service)
):
    """
    转录上传的视频文件

    Args:
        file: 上传的视频文件
        model: Whisper 模型
        language: 目标语言
        format: 输出格式
        timestamps: 是否包含时间戳
        background_tasks: 后台任务
        service: 转录服务
        file_service: 文件服务

    Returns:
        TranscribeResponse: 转录结果
    """
    try:
        # 保存上传的文件
        temp_dir = file_service.ensure_directory(settings.temp_path)
        safe_filename = file_service.get_safe_filename(file.filename)
        file_path = file_service.get_unique_filepath(
            str(temp_dir),
            safe_filename,
            Path(file.filename).suffix
        )

        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # 验证文件
        is_valid, error_msg = await file_service.validate_file(
            file_path,
            settings.MAX_FILE_SIZE
        )

        if not is_valid:
            # 清理文件
            Path(file_path).unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=error_msg)

        # 准备处理选项
        options = ProcessOptions(
            model=WhisperModel(model),
            language=Language(language),
            with_timestamps=timestamps,
            output_format=OutputFormat(format),
            enable_gpu=settings.ENABLE_GPU,
            temperature=settings.DEFAULT_TEMPERATURE
        )

        # 执行转录
        result = await service.transcribe_file(file_path, options)

        # 清理临时文件
        background_tasks.add_task(lambda: Path(file_path).unlink(missing_ok=True))

        return TranscribeResponse(
            success=True,
            task_id="",
            result=result,
            message="转录完成"
        )

    except Exception as e:
        logger.error(f"文件转录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@transcribe_router.post("/batch")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def transcribe_batch(
    file_paths: List[str],
    model: str = Form(default=settings.DEFAULT_MODEL),
    language: str = Form(default="auto"),
    format: str = Form(default="txt"),
    max_concurrent: int = Form(default=3),
    service: TranscriptionService = Depends(get_transcription_service)
):
    """
    批量转录视频文件

    Args:
        file_paths: 文件路径列表
        model: Whisper 模型
        language: 目标语言
        format: 输出格式
        max_concurrent: 最大并发数
        service: 转录服务

    Returns:
        dict: 批量处理结果
    """
    try:
        # 准备处理选项
        options = ProcessOptions(
            model=WhisperModel(model),
            language=Language(language),
            with_timestamps=False,
            output_format=OutputFormat(format),
            enable_gpu=settings.ENABLE_GPU,
            temperature=settings.DEFAULT_TEMPERATURE
        )

        # 执行批量转录
        result = await service.transcribe_batch(
            file_paths=file_paths,
            options=options,
            max_concurrent=max_concurrent
        )

        return {
            "success": True,
            "data": result
        }

    except Exception as e:
        logger.error(f"批量转录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================
# 任务查询端点
# ============================================================

@transcribe_router.get("/task/{task_id}")
async def get_task_status(
    task_id: str,
    service: TranscriptionService = Depends(get_transcription_service)
):
    """
    获取任务状态

    Args:
        task_id: 任务 ID
        service: 转录服务

    Returns:
        dict: 任务状态
    """
    task = service.get_task_status(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    return {
        "success": True,
        "data": task.model_dump()
    }


@transcribe_router.get("/tasks")
async def list_tasks(
    limit: int = 10,
    status: Optional[str] = None,
    service: TranscriptionService = Depends(get_transcription_service)
):
    """
    列出最近的任务

    Args:
        limit: 返回数量限制
        status: 状态过滤
        service: 转录服务

    Returns:
        dict: 任务列表
    """
    # 这里需要在 TaskService 中添加对应的方法
    return {
        "success": True,
        "data": {
            "tasks": [],
            "total": 0
        }
    }


@transcribe_router.get("/stats")
async def get_statistics(
    service: TranscriptionService = Depends(get_transcription_service)
):
    """
    获取统计信息

    Args:
        service: 转录服务

    Returns:
        dict: 统计信息
    """
    stats = service.get_statistics()
    return {
        "success": True,
        "data": stats
    }
