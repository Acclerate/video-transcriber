"""
系统路由
处理模型信息、系统清理等 API 端点
"""

from fastapi import APIRouter, HTTPException
from loguru import logger

from config import settings
from models.schemas import APIResponse
from services import TranscriptionService


system_router = APIRouter(
    prefix="/api/v1",
    tags=["系统管理"]
)

_transcription_service = TranscriptionService()


@system_router.get("/models")
async def get_available_models():
    """获取可用的语音识别模型"""
    try:
        models_info = {
            "sensevoice-small": {
                "name": "SenseVoice Small",
                "size": "244MB",
                "description": "多语言语音识别，中文优化",
                "languages": ["中文", "英文", "日语", "韩语", "粤语", "法语", "西班牙语"],
                "speed": "4x",
                "accuracy": "★★★★☆"
            }
        }

        current_model = {
            "name": models_info.get(settings.DEFAULT_MODEL, {}).get("name", settings.DEFAULT_MODEL),
            "value": settings.DEFAULT_MODEL
        }

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


@system_router.post("/cleanup")
async def cleanup_system():
    """清理系统"""
    try:
        cleaned_tasks = await _transcription_service.cleanup_old_tasks(24)
        cleaned_files = await _transcription_service.cleanup_temp_files()

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
