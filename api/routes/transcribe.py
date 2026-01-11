"""
转录路由
处理视频转录相关的 API 端点
"""

from typing import Optional, List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Request
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
    request: Request,
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

        # 清理临时文件 - 创建清理函数
        def cleanup_file(file_to_remove: str):
            """后台清理文件函数"""
            try:
                Path(file_to_remove).unlink(missing_ok=True)
                logger.debug(f"已清理临时文件: {file_to_remove}")
            except Exception as e:
                logger.warning(f"清理文件失败 {file_to_remove}: {e}")

        background_tasks.add_task(cleanup_file, file_path)

        return TranscribeResponse(
            code=200,
            message="转录完成",
            data={"transcription": result.model_dump()}
        )

    except Exception as e:
        logger.error(f"文件转录失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@transcribe_router.post("/batch")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def transcribe_batch(
    request: Request,
    files: List[UploadFile] = File(..., description="要转录的视频文件列表"),
    model: str = Form(default=settings.DEFAULT_MODEL),
    language: str = Form(default="auto"),
    format: str = Form(default="txt"),
    max_concurrent: int = Form(default=3),
    background_tasks: BackgroundTasks = None,
    service: TranscriptionService = Depends(get_transcription_service),
    file_service: FileService = Depends(get_file_service)
):
    """
    批量转录视频文件

    Args:
        files: 上传的视频文件列表 (最多20个)
        model: Whisper 模型
        language: 目标语言
        format: 输出格式
        max_concurrent: 最大并发数 (1-10)
        background_tasks: 后台任务
        service: 转录服务
        file_service: 文件服务

    Returns:
        dict: 批量处理结果
    """
    temp_dir = file_service.ensure_directory(settings.temp_path)
    saved_files = []

    try:
        # 验证文件数量
        if len(files) > 20:
            raise HTTPException(
                status_code=400,
                detail=f"文件数量超过限制，最多支持20个文件，当前上传了{len(files)}个"
            )

        # 验证并发数
        if not 1 <= max_concurrent <= 10:
            raise HTTPException(
                status_code=400,
                detail="max_concurrent 必须在 1-10 之间"
            )

        # 保存上传的文件
        for file in files:
            # 生成安全的文件名
            safe_filename = file_service.get_safe_filename(file.filename)
            file_path = file_service.get_unique_filepath(
                str(temp_dir),
                safe_filename,
                Path(file.filename).suffix
            )

            # 保存文件
            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)

            # 验证文件
            is_valid, error_msg = await file_service.validate_file(
                file_path,
                settings.MAX_FILE_SIZE
            )

            if not is_valid:
                # 清理已保存的文件
                for saved_file in saved_files:
                    Path(saved_file).unlink(missing_ok=True)
                Path(file_path).unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail=f"{file.filename}: {error_msg}")

            saved_files.append(file_path)

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
            file_paths=saved_files,
            options=options,
            max_concurrent=max_concurrent
        )

        # 后台清理文件
        def cleanup_batch_files():
            for file_path in saved_files:
                try:
                    Path(file_path).unlink(missing_ok=True)
                    logger.debug(f"已清理临时文件: {file_path}")
                except Exception as e:
                    logger.warning(f"清理文件失败 {file_path}: {e}")

        if background_tasks:
            background_tasks.add_task(cleanup_batch_files)

        return {
            "code": 200,
            "data": result,
            "message": f"批量处理完成: {result.get('success', 0)}/{result.get('total', 0)} 成功"
        }

    except HTTPException:
        # 清理已保存的文件
        for saved_file in saved_files:
            Path(saved_file).unlink(missing_ok=True)
        raise
    except Exception as e:
        logger.error(f"批量转录失败: {e}")
        # 清理已保存的文件
        for saved_file in saved_files:
            Path(saved_file).unlink(missing_ok=True)
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
        "code": 200,
        "data": task.model_dump(),
        "message": "查询成功"
    }


@transcribe_router.get("/tasks")
async def list_tasks(
    limit: int = 10,
    status: Optional[str] = None,
    offset: int = 0,
    service: TranscriptionService = Depends(get_transcription_service)
):
    """
    列出最近的任务

    Args:
        limit: 返回数量限制 (1-100)
        status: 状态过滤 (pending/extracting/transcribing/completed/failed/cancelled)
        offset: 偏移量（用于分页）
        service: 转录服务

    Returns:
        dict: 任务列表
    """
    try:
        # 验证参数
        if not 1 <= limit <= 100:
            raise HTTPException(
                status_code=400,
                detail="limit 必须在 1-100 之间"
            )

        if offset < 0:
            raise HTTPException(
                status_code=400,
                detail="offset 必须大于等于 0"
            )

        # 解析状态过滤
        status_filter = None
        if status:
            try:
                from models.schemas import TaskStatus
                status_filter = TaskStatus(status.lower())
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"无效的状态值: {status}。有效值为: pending, extracting, transcribing, completed, failed, cancelled"
                )

        # 获取任务列表
        tasks = service.task_service.get_recent_tasks(
            limit=limit + offset,  # 多取一些用于分页
            status=status_filter
        )

        # 应用分页
        paginated_tasks = tasks[offset:offset + limit]
        total_count = len(tasks)

        # 转换为字典格式（移除内部数据）
        task_list = []
        for task in paginated_tasks:
            task_dict = task.model_dump(exclude_none=True)
            # 简化返回的数据，避免过大
            if "result" in task_dict and task_dict["result"]:
                result = task_dict["result"]
                # 只保留关键信息
                task_dict["result"] = {
                    "text": result.text[:100] + "..." if len(result.text) > 100 else result.text,
                    "language": result.language,
                    "confidence": result.confidence,
                    "processing_time": result.processing_time
                }
            task_list.append(task_dict)

        return {
            "code": 200,
            "data": {
                "tasks": task_list,
                "total": total_count,
                "limit": limit,
                "offset": offset,
                "has_more": offset + len(task_list) < total_count
            },
            "message": "查询成功"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"获取任务列表失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
        "code": 200,
        "data": stats,
        "message": "查询成功"
    }
