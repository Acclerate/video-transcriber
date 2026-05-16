"""
API 路由模块
包含所有 API 路由处理
"""

from .health import health_router
from .transcribe import transcribe_router
from .tasks import task_router
from .system import system_router

__all__ = [
    "health_router",
    "transcribe_router",
    "task_router",
    "system_router",
]
