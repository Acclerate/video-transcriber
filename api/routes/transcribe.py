"""
转录路由
处理媒体转录相关的 API 端点
"""

from collections import deque
import asyncio
from typing import Optional, List, Deque
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address
from loguru import logger

from config import settings
from models.schemas import (
    ProcessOptions, APIResponse, TranscribeResponse,
    TranscriptionResult, TranscriptionModel, Language, OutputFormat
)
from services import TranscriptionService, FileService


# 速率限制器
limiter = Limiter(key_func=get_remote_address)

# 创建路由器
transcribe_router = APIRouter(
    prefix="/api/v1/transcribe",
    tags=["转录服务"]
)


# 模型名称映射 (支持旧模型名称的兼容性)
MODEL_NAME_MAP = {
    "tiny": "sensevoice-small",
    "base": "sensevoice-small",
    "small": "sensevoice-small",
    "medium": "sensevoice-small",
    "large": "sensevoice-small",
    "sensevoice-small": "sensevoice-small",
}


def normalize_model_name(model: str) -> str:
    """规范化模型名称，支持旧模型名称的兼容性"""
    model_lower = model.lower().strip()
    return MODEL_NAME_MAP.get(model_lower, "sensevoice-small")


# 依赖注入
_transcription_service = TranscriptionService()
_file_service = FileService()


def get_transcription_service() -> TranscriptionService:
    """获取转录服务实例"""
    return _transcription_service


def get_file_service() -> FileService:
    """获取文件服务实例"""
    return _file_service


def tail_file_lines(file_path: Path, max_lines: int = 200) -> List[str]:
    """高效读取文件末尾的若干行。"""
    if max_lines <= 0:
        return []

    line_buffer: Deque[str] = deque(maxlen=max_lines)

    with file_path.open("r", encoding="utf-8", errors="replace") as log_file:
        for line in log_file:
            line_buffer.append(line.rstrip("\n"))

    return list(line_buffer)


def detect_log_level(line: str) -> str:
    """从日志行中提取级别（error/warning/info/debug）。"""
    upper_line = line.upper()
    if "| ERROR" in upper_line or "| CRITICAL" in upper_line:
        return "error"
    if "| WARNING" in upper_line or "| WARN" in upper_line:
        return "warning"
    if "| DEBUG" in upper_line:
        return "debug"
    return "info"


# ============================================================
# 转录端点
# ============================================================

@transcribe_router.post("/file")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def transcribe_file(
    request: Request,
    file: UploadFile = File(...),
    model: str = Form(default=settings.DEFAULT_MODEL),
    language: str = Form(default="auto"),
    format: str = Form(default="txt"),
    timestamps: bool = Form(default=False),
    service: TranscriptionService = Depends(get_transcription_service),
    file_service: FileService = Depends(get_file_service)
):
    """
    转录上传的媒体文件（异步任务模式）

    提交后立即返回 task_id，通过 GET /task/{task_id} 轮询进度和结果。
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
            Path(file_path).unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=error_msg)

        # 准备处理选项
        normalized_model = normalize_model_name(model)
        options = ProcessOptions(
            model=TranscriptionModel(normalized_model),
            language=Language(language),
            with_timestamps=timestamps,
            output_format=OutputFormat(format),
            enable_gpu=settings.ENABLE_GPU,
            temperature=settings.DEFAULT_TEMPERATURE
        )

        # 创建任务并后台执行
        task_id = service.create_task_id()
        service.register_task_temp_file(task_id, file_path)
        asyncio.create_task(
            service.transcribe_file(file_path, options, task_id=task_id)
        )

        return JSONResponse(
            status_code=202,
            content={
                "code": 202,
                "message": "任务已提交",
                "data": {"task_id": task_id}
            }
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"文件转录提交失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@transcribe_router.post("/batch")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def transcribe_batch(
    request: Request,
    files: List[UploadFile] = File(..., description="要转录的媒体文件列表"),
    model: str = Form(default=settings.DEFAULT_MODEL),
    language: str = Form(default="auto"),
    format: str = Form(default="txt"),
    max_concurrent: int = Form(default=3),
    service: TranscriptionService = Depends(get_transcription_service),
    file_service: FileService = Depends(get_file_service)
):
    """
    批量转录媒体文件（异步任务模式）

    每个文件创建独立任务，提交后立即返回 task_id 列表。
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
            safe_filename = file_service.get_safe_filename(file.filename)
            file_path = file_service.get_unique_filepath(
                str(temp_dir),
                safe_filename,
                Path(file.filename).suffix
            )

            with open(file_path, "wb") as f:
                content = await file.read()
                f.write(content)

            is_valid, error_msg = await file_service.validate_file(
                file_path,
                settings.MAX_FILE_SIZE
            )

            if not is_valid:
                for saved_file in saved_files:
                    Path(saved_file).unlink(missing_ok=True)
                Path(file_path).unlink(missing_ok=True)
                raise HTTPException(status_code=400, detail=f"{file.filename}: {error_msg}")

            saved_files.append((file_path, file.filename))

        # 准备处理选项
        normalized_model = normalize_model_name(model)
        options = ProcessOptions(
            model=TranscriptionModel(normalized_model),
            language=Language(language),
            with_timestamps=False,
            output_format=OutputFormat(format),
            enable_gpu=settings.ENABLE_GPU,
            temperature=settings.DEFAULT_TEMPERATURE
        )

        # 为每个文件创建独立任务并后台执行
        semaphore = asyncio.Semaphore(max_concurrent)

        async def run_with_semaphore(fp, opts, tid):
            async with semaphore:
                await service.transcribe_file(fp, opts, task_id=tid)

        task_list = []
        for file_path, filename in saved_files:
            task_id = service.create_task_id()
            service.register_task_temp_file(task_id, file_path)
            asyncio.create_task(run_with_semaphore(file_path, options, task_id))
            task_list.append({"task_id": task_id, "file": filename})

        return JSONResponse(
            status_code=202,
            content={
                "code": 202,
                "message": f"已提交 {len(task_list)} 个转录任务",
                "data": {"tasks": task_list, "total": len(task_list)}
            }
        )

    except HTTPException:
        for saved_file in saved_files:
            if isinstance(saved_file, tuple):
                Path(saved_file[0]).unlink(missing_ok=True)
            else:
                Path(saved_file).unlink(missing_ok=True)
        raise
    except Exception as e:
        logger.error(f"批量转录提交失败: {e}")
        for saved_file in saved_files:
            if isinstance(saved_file, tuple):
                Path(saved_file[0]).unlink(missing_ok=True)
            else:
                Path(saved_file).unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=str(e))


@transcribe_router.post("/task/{task_id}/cancel")
async def cancel_task(
    task_id: str,
    service: TranscriptionService = Depends(get_transcription_service)
):
    """终止指定任务，并清理任务产生的临时文件。"""
    result = await service.cancel_task(task_id)

    if not result["success"]:
        if result["reason"] == "not_found":
            raise HTTPException(status_code=404, detail=result["message"])
        raise HTTPException(status_code=409, detail=result["message"])

    return {
        "code": 200,
        "message": result["message"],
        "data": {
            "task_id": task_id,
            "status": "cancel_requested"
        }
    }


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
                    "text": result["text"][:100] + "..." if len(result["text"]) > 100 else result["text"],
                    "language": result.get("language"),
                    "confidence": result.get("confidence"),
                    "processing_time": result.get("processing_time")
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


@transcribe_router.get("/logs")
async def get_transcription_logs(
    limit: int = 120,
    level: str = "all",
    keyword: str = "",
):
    """
    获取最近的后端日志（面向前端日志面板）。

    Args:
        limit: 返回的最大行数 (10-500)
        level: 日志级别过滤（all/debug/info/warning/error）
        keyword: 可选关键字过滤（大小写不敏感）

    Returns:
        dict: 日志行与基础统计
    """
    try:
        limit = max(10, min(limit, 500))
        normalized_level = (level or "all").strip().lower()
        valid_levels = {"all", "debug", "info", "warning", "error"}
        if normalized_level not in valid_levels:
            raise HTTPException(status_code=400, detail="无效的 level 参数")

        log_file = settings.log_file_path

        if not log_file.exists():
            return {
                "code": 200,
                "data": {
                    "lines": [],
                    "total": 0,
                    "level": normalized_level,
                    "keyword": keyword,
                    "source": str(log_file),
                    "updated_at": None,
                },
                "message": "日志文件不存在"
            }

        lines = tail_file_lines(log_file, max_lines=limit * 4)

        # 默认聚焦转录相关日志，若指定 keyword 则按 keyword 过滤
        if keyword.strip():
            keyword_lower = keyword.lower().strip()
            filtered = [line for line in lines if keyword_lower in line.lower()]
        else:
            default_keywords = (
                "转录", "transcrib", "sensevoice", "audio", "ffmpeg", "task", "批量"
            )
            filtered = [
                line for line in lines
                if any(k in line.lower() for k in default_keywords)
            ]

        if normalized_level != "all":
            filtered = [
                line for line in filtered
                if detect_log_level(line) == normalized_level
            ]

        result_lines = filtered[-limit:]

        return {
            "code": 200,
            "data": {
                "lines": result_lines,
                "total": len(result_lines),
                "level": normalized_level,
                "keyword": keyword,
                "source": str(log_file),
                "updated_at": log_file.stat().st_mtime,
            },
            "message": "查询成功"
        }

    except Exception as e:
        logger.error(f"获取日志失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))
