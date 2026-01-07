"""
API 路由模块
包含所有 API 路由处理
"""

from .health import health_router
from .transcribe import transcribe_router

__all__ = [
    "health_router",
    "transcribe_router",
]
