"""
WebSocket处理模块
提供实时进度更新和结果推送
"""

import json
import asyncio
import time
from typing import Dict, Set
from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger

from models.schemas import (
    WSMessage, WSProgressMessage, WSResultMessage, WSErrorMessage,
    WSMessageType, TranscribeRequest, ProcessOptions
)
from core import transcription_engine
from utils import validate_url


class WebSocketManager:
    """WebSocket连接管理器"""

    # 默认心跳超时时间（秒）
    HEARTBEAT_TIMEOUT = 300  # 5分钟无活动则断开

    def __init__(self, heartbeat_timeout: int = None):
        # 活跃连接
        self.active_connections: Set[WebSocket] = set()
        # 任务订阅映射
        self.task_subscriptions: Dict[str, Set[WebSocket]] = {}
        # 连接最后活动时间
        self.connection_last_activity: Dict[WebSocket, float] = {}
        # 心跳超时时间
        self.heartbeat_timeout = heartbeat_timeout or self.HEARTBEAT_TIMEOUT

        # 启动心跳检查任务
        self._heartbeat_task = None
    
    async def connect(self, websocket: WebSocket) -> bool:
        """接受WebSocket连接"""
        try:
            await websocket.accept()
            self.active_connections.add(websocket)
            self.connection_last_activity[websocket] = time.time()

            # 启动心跳检查任务
            if self._heartbeat_task is None:
                self._heartbeat_task = asyncio.create_task(self._heartbeat_checker())

            logger.info(f"WebSocket连接建立: {websocket.client}")
            return True
        except Exception as e:
            logger.error(f"WebSocket连接失败: {e}")
            return False

    def disconnect(self, websocket: WebSocket):
        """断开WebSocket连接"""
        try:
            self.active_connections.discard(websocket)

            # 清理任务订阅
            for task_id, subscribers in list(self.task_subscriptions.items()):
                subscribers.discard(websocket)
                if not subscribers:
                    del self.task_subscriptions[task_id]

            # 清理活动时间记录
            self.connection_last_activity.pop(websocket, None)

            logger.info(f"WebSocket连接断开: {websocket.client}")
        except Exception as e:
            logger.error(f"WebSocket断开处理失败: {e}")

    def update_activity(self, websocket: WebSocket):
        """更新连接活动时间"""
        self.connection_last_activity[websocket] = time.time()

    async def _heartbeat_checker(self):
        """心跳检查任务"""
        while True:
            try:
                await asyncio.sleep(60)  # 每分钟检查一次
                current_time = time.time()

                # 检查超时连接
                timeout_connections = []
                for websocket, last_activity in list(self.connection_last_activity.items()):
                    if current_time - last_activity > self.heartbeat_timeout:
                        timeout_connections.append(websocket)

                # 断开超时连接
                for websocket in timeout_connections:
                    logger.warning(f"WebSocket连接超时，断开: {websocket.client}")
                    try:
                        await websocket.close(code=1000, reason="heartbeat timeout")
                    except Exception:
                        pass
                    self.disconnect(websocket)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳检查失败: {e}")
    
    async def send_message(self, websocket: WebSocket, message: WSMessage):
        """发送消息到指定WebSocket"""
        try:
            await websocket.send_text(message.model_dump_json())
        except Exception as e:
            logger.error(f"WebSocket消息发送失败: {e}")
            self.disconnect(websocket)
    
    async def broadcast_message(self, message: WSMessage):
        """广播消息到所有连接"""
        if not self.active_connections:
            return
        
        disconnected = set()
        
        for websocket in self.active_connections:
            try:
                await websocket.send_text(message.model_dump_json())
            except Exception as e:
                logger.error(f"广播消息失败: {e}")
                disconnected.add(websocket)
        
        # 清理断开的连接
        for websocket in disconnected:
            self.disconnect(websocket)
    
    async def send_to_task_subscribers(self, task_id: str, message: WSMessage):
        """发送消息到任务订阅者"""
        if task_id not in self.task_subscriptions:
            return
        
        subscribers = self.task_subscriptions[task_id].copy()
        disconnected = set()
        
        for websocket in subscribers:
            try:
                await websocket.send_text(message.model_dump_json())
            except Exception as e:
                logger.error(f"任务消息发送失败: {e}")
                disconnected.add(websocket)
        
        # 清理断开的连接
        for websocket in disconnected:
            self.disconnect(websocket)
    
    def subscribe_to_task(self, websocket: WebSocket, task_id: str):
        """订阅任务更新"""
        if task_id not in self.task_subscriptions:
            self.task_subscriptions[task_id] = set()
        
        self.task_subscriptions[task_id].add(websocket)
        logger.debug(f"WebSocket订阅任务: {task_id}")
    
    def unsubscribe_from_task(self, websocket: WebSocket, task_id: str):
        """取消订阅任务"""
        if task_id in self.task_subscriptions:
            self.task_subscriptions[task_id].discard(websocket)
            
            if not self.task_subscriptions[task_id]:
                del self.task_subscriptions[task_id]
        
        logger.debug(f"WebSocket取消订阅任务: {task_id}")
    
    def get_connection_count(self) -> int:
        """获取活跃连接数"""
        return len(self.active_connections)
    
    def get_task_subscriber_count(self, task_id: str) -> int:
        """获取任务订阅者数量"""
        return len(self.task_subscriptions.get(task_id, set()))


# 全局WebSocket管理器
ws_manager = WebSocketManager()


async def handle_websocket_message(websocket: WebSocket, message: dict):
    """处理WebSocket消息"""
    try:
        action = message.get("action")
        data = message.get("data", {})
        
        if action == "transcribe":
            # 处理转录请求
            await handle_transcribe_request(websocket, data)
        elif action == "subscribe":
            # 订阅任务更新
            task_id = data.get("task_id")
            if task_id:
                ws_manager.subscribe_to_task(websocket, task_id)
                await ws_manager.send_message(websocket, WSMessage(
                    type=WSMessageType.PROGRESS,
                    data={"message": f"已订阅任务: {task_id}"}
                ))
        elif action == "unsubscribe":
            # 取消订阅
            task_id = data.get("task_id")
            if task_id:
                ws_manager.unsubscribe_from_task(websocket, task_id)
                await ws_manager.send_message(websocket, WSMessage(
                    type=WSMessageType.PROGRESS,
                    data={"message": f"已取消订阅: {task_id}"}
                ))
        elif action == "ping":
            # 心跳检测
            await ws_manager.send_message(websocket, WSMessage(
                type=WSMessageType.PONG,
                data={"message": "pong"}
            ))
        else:
            # 未知动作
            await ws_manager.send_message(websocket, WSErrorMessage(
                type=WSMessageType.ERROR,
                data={"error": "未知的动作", "action": str(action) if action else "unknown"}
            ))
    
    except Exception as e:
        logger.error(f"WebSocket消息处理失败: {e}")
        await ws_manager.send_message(websocket, WSErrorMessage(
            type=WSMessageType.ERROR,
            data={"error": f"消息处理失败: {str(e)}"}
        ))


async def handle_transcribe_request(websocket: WebSocket, data: dict):
    """处理转录请求"""
    try:
        # 验证请求数据
        url = data.get("url")
        if not url:
            raise ValueError("缺少视频链接")

        if not validate_url(url):
            raise ValueError("无效的视频链接")

        # 解析选项
        options_data = data.get("options", {})
        options = ProcessOptions(**options_data)

        # 创建进度回调
        def progress_callback(task_id: str, progress: float, message: str):
            asyncio.create_task(ws_manager.send_message(websocket, WSProgressMessage(
                type=WSMessageType.PROGRESS,
                data={
                    "task_id": task_id,
                    "progress": progress,
                    "message": message
                }
            )))

        # 发送开始消息
        await ws_manager.send_message(websocket, WSProgressMessage(
            type=WSMessageType.PROGRESS,
            data={"message": "开始处理视频..."}
        ))

        # 执行转录
        result = await transcription_engine.process_video_url(
            url=url,
            options=options,
            progress_callback=progress_callback
        )

        # 发送结果
        await ws_manager.send_message(websocket, WSResultMessage(
            type=WSMessageType.RESULT,
            data={
                "text": result.text,
                "language": result.language,
                "confidence": result.confidence,
                "processing_time": result.processing_time
            }
        ))

    except NotImplementedError as e:
        # URL下载功能未实现
        logger.warning(f"URL处理请求被拒绝: {e}")
        await ws_manager.send_message(websocket, WSErrorMessage(
            type=WSMessageType.ERROR,
            data={
                "error": "URL视频处理功能暂未启用",
                "details": "请使用文件上传方式处理视频",
                "suggestion": "通过 Web 界面或 POST /api/v1/transcribe/file 上传本地视频文件"
            }
        ))
    except Exception as e:
        logger.error(f"WebSocket转录请求处理失败: {e}")
        await ws_manager.send_message(websocket, WSErrorMessage(
            type=WSMessageType.ERROR,
            data={"error": f"转录失败: {str(e)}"}
        ))


async def websocket_endpoint(websocket: WebSocket):
    """WebSocket端点处理函数"""
    if not await ws_manager.connect(websocket):
        return

    try:
        # 发送欢迎消息
        welcome_message = WSMessage(
            type=WSMessageType.PROGRESS,
            data={"message": "WebSocket连接成功"}
        )
        await ws_manager.send_message(websocket, welcome_message)

        # 消息循环
        while True:
            try:
                # 接收消息
                raw_message = await websocket.receive_text()

                # 更新活动时间
                ws_manager.update_activity(websocket)

                # 解析JSON消息
                try:
                    message = json.loads(raw_message)
                except json.JSONDecodeError:
                    await ws_manager.send_message(websocket, WSErrorMessage(
                        type=WSMessageType.ERROR,
                        data={"error": "无效的JSON格式"}
                    ))
                    continue

                # 处理消息
                await handle_websocket_message(websocket, message)

            except WebSocketDisconnect:
                logger.info("WebSocket客户端主动断开连接")
                break
            except Exception as e:
                logger.error(f"WebSocket消息接收失败: {e}")
                await ws_manager.send_message(websocket, WSErrorMessage(
                    type=WSMessageType.ERROR,
                    data={"error": f"消息处理错误: {str(e)}"}
                ))

    except Exception as e:
        logger.error(f"WebSocket处理异常: {e}")
    finally:
        ws_manager.disconnect(websocket)


# 任务进度广播辅助函数
async def broadcast_task_progress(task_id: str, progress: float, message: str):
    """广播任务进度"""
    progress_message = WSProgressMessage(
        type=WSMessageType.PROGRESS,
        data={
            "task_id": task_id,
            "progress": progress,
            "message": message
        }
    )
    await ws_manager.send_to_task_subscribers(task_id, progress_message)


async def broadcast_task_result(task_id: str, result: dict):
    """广播任务结果"""
    result_message = WSResultMessage(
        type=WSMessageType.RESULT,
        data={
            "task_id": task_id,
            "text": result.get("text", ""),
            "language": result.get("language", "unknown"),
            "confidence": result.get("confidence", 0.0)
        }
    )
    await ws_manager.send_to_task_subscribers(task_id, result_message)


async def broadcast_task_error(task_id: str, error: str):
    """广播任务错误"""
    error_message = WSErrorMessage(
        type=WSMessageType.ERROR,
        data={
            "task_id": task_id,
            "error": error
        }
    )
    await ws_manager.send_to_task_subscribers(task_id, error_message)


if __name__ == "__main__":
    # 测试WebSocket管理器
    import asyncio
    from unittest.mock import MagicMock
    
    async def test():
        manager = WebSocketManager()
        
        # 模拟WebSocket
        mock_ws1 = MagicMock()
        mock_ws2 = MagicMock()
        
        print(f"连接数: {manager.get_connection_count()}")
        
        # 模拟订阅
        manager.subscribe_to_task(mock_ws1, "task_1")
        manager.subscribe_to_task(mock_ws2, "task_1")
        
        print(f"任务订阅数: {manager.get_task_subscriber_count('task_1')}")
        
        # 模拟取消订阅
        manager.unsubscribe_from_task(mock_ws1, "task_1")
        
        print(f"任务订阅数: {manager.get_task_subscriber_count('task_1')}")
    
    # asyncio.run(test())