"""
任务查询路由
处理任务状态查询相关的 API 端点
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from models.schemas import TaskStatusResponse, APIResponse
from services import TranscriptionService


task_router = APIRouter(
    prefix="/api/v1",
    tags=["任务查询"]
)

_transcription_service = TranscriptionService()


@task_router.get("/status/{task_id}")
async def get_task_status(task_id: str):
    """查询任务状态"""
    try:
        task_info = _transcription_service.get_task_status(task_id)

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


@task_router.get("/batch-status/{batch_id}")
async def get_batch_status(batch_id: str):
    """查询批量任务状态"""
    try:
        from core.engine import transcription_engine

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
