"""
任务服务
管理转录任务的状态和统计
"""

import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

from loguru import logger

from config import settings
from models.schemas import TaskInfo, TaskStatus, BatchTaskInfo


class TaskService:
    """
    任务服务
    管理所有转录任务的状态、生命周期和统计信息
    """

    def __init__(self, config: Optional[settings] = None):
        """
        初始化任务服务

        Args:
            config: 应用配置
        """
        self.config = config or settings

        # 任务存储
        self.tasks: Dict[str, TaskInfo] = {}
        self.batch_tasks: Dict[str, BatchTaskInfo] = {}

        # 统计信息
        self.stats = {
            "total_processed": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_processing_time": 0.0,
            "total_characters": 0,
        }

        # 按状态分组的任务
        self.tasks_by_status: Dict[str, List[str]] = defaultdict(list)

        logger.debug("任务服务初始化完成")

    # ============================================================
    # 任务管理
    # ============================================================

    def add_task(self, task_id: str, task_info: TaskInfo) -> None:
        """
        添加任务

        Args:
            task_id: 任务 ID
            task_info: 任务信息
        """
        self.tasks[task_id] = task_info
        self.tasks_by_status[task_info.status.value].append(task_id)
        logger.debug(f"添加任务: {task_id}")

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """
        获取任务

        Args:
            task_id: 任务 ID

        Returns:
            Optional[TaskInfo]: 任务信息
        """
        return self.tasks.get(task_id)

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None,
        progress: Optional[int] = None
    ) -> bool:
        """
        更新任务状态

        Args:
            task_id: 任务 ID
            status: 新状态
            error_message: 错误消息
            progress: 进度值

        Returns:
            bool: 是否更新成功
        """
        task = self.tasks.get(task_id)
        if not task:
            return False

        # 从旧状态列表中移除
        if task.status.value in self.tasks_by_status:
            try:
                self.tasks_by_status[task.status.value].remove(task_id)
            except ValueError:
                pass

        # 更新任务信息
        old_status = task.status
        task.status = status
        task.progress = progress or task.progress

        if error_message:
            task.error_message = error_message

        if status == TaskStatus.COMPLETED:
            task.completed_at = datetime.now()
        elif status == TaskStatus.FAILED:
            task.completed_at = datetime.now()

        # 添加到新状态列表
        self.tasks_by_status[status.value].append(task_id)

        logger.debug(f"任务状态更新: {task_id} {old_status.value} -> {status.value}")
        return True

    def remove_task(self, task_id: str) -> bool:
        """
        移除任务

        Args:
            task_id: 任务 ID

        Returns:
            bool: 是否移除成功
        """
        task = self.tasks.get(task_id)
        if not task:
            return False

        # 从状态列表中移除
        if task.status.value in self.tasks_by_status:
            try:
                self.tasks_by_status[task.status.value].remove(task_id)
            except ValueError:
                pass

        del self.tasks[task_id]
        logger.debug(f"移除任务: {task_id}")
        return True

    # ============================================================
    # 批量任务管理
    # ============================================================

    def create_batch_task(
        self,
        batch_id: str,
        total_count: int
    ) -> BatchTaskInfo:
        """
        创建批量任务

        Args:
            batch_id: 批量任务 ID
            total_count: 总任务数

        Returns:
            BatchTaskInfo: 批量任务信息
        """
        batch_info = BatchTaskInfo(
            batch_id=batch_id,
            total_count=total_count,
            pending_count=total_count,
            completed_count=0,
            failed_count=0,
            created_at=datetime.now()
        )
        self.batch_tasks[batch_id] = batch_info
        return batch_info

    def get_batch_task(self, batch_id: str) -> Optional[BatchTaskInfo]:
        """
        获取批量任务

        Args:
            batch_id: 批量任务 ID

        Returns:
            Optional[BatchTaskInfo]: 批量任务信息
        """
        return self.batch_tasks.get(batch_id)

    def update_batch_task(
        self,
        batch_id: str,
        completed: int = 0,
        failed: int = 0
    ) -> bool:
        """
        更新批量任务统计

        Args:
            batch_id: 批量任务 ID
            completed: 完成的任务数
            failed: 失败的任务数

        Returns:
            bool: 是否更新成功
        """
        batch_info = self.batch_tasks.get(batch_id)
        if not batch_info:
            return False

        batch_info.completed_count += completed
        batch_info.failed_count += failed
        batch_info.pending_count -= (completed + failed)

        return True

    # ============================================================
    # 查询方法
    # ============================================================

    def get_tasks_by_status(self, status: TaskStatus) -> List[TaskInfo]:
        """
        按状态获取任务列表

        Args:
            status: 任务状态

        Returns:
            List[TaskInfo]: 任务列表
        """
        task_ids = self.tasks_by_status.get(status.value, [])
        return [self.tasks[tid] for tid in task_ids if tid in self.tasks]

    def get_active_tasks(self) -> List[TaskInfo]:
        """
        获取活动中的任务

        Returns:
            List[TaskInfo]: 活动任务列表
        """
        active_statuses = [
            TaskStatus.PENDING,
            TaskStatus.EXTRACTING,
            TaskStatus.TRANSCRIBING
        ]
        active_tasks = []
        for status in active_statuses:
            active_tasks.extend(self.get_tasks_by_status(status))
        return active_tasks

    def get_recent_tasks(
        self,
        limit: int = 10,
        status: Optional[TaskStatus] = None
    ) -> List[TaskInfo]:
        """
        获取最近的任务

        Args:
            limit: 返回数量限制
            status: 状态过滤（可选）

        Returns:
            List[TaskInfo]: 任务列表
        """
        tasks = list(self.tasks.values())

        # 状态过滤
        if status:
            tasks = [t for t in tasks if t.status == status]

        # 按创建时间排序
        tasks.sort(
            key=lambda t: t.started_at or datetime.min,
            reverse=True
        )

        return tasks[:limit]

    # ============================================================
    # 统计信息
    # ============================================================

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取统计信息

        Returns:
            Dict[str, Any]: 统计信息
        """
        active_tasks = self.get_active_tasks()

        return {
            "total_tasks": len(self.tasks),
            "active_tasks": len(active_tasks),
            "total_processed": self.stats["total_processed"],
            "total_success": self.stats["total_success"],
            "total_failed": self.stats["total_failed"],
            "success_rate": (
                self.stats["total_success"] / self.stats["total_processed"]
                if self.stats["total_processed"] > 0
                else 0
            ),
            "average_processing_time": (
                self.stats["total_processing_time"] / self.stats["total_processed"]
                if self.stats["total_processed"] > 0
                else 0
            ),
            "total_characters": self.stats["total_characters"],
            "tasks_by_status": {
                status: len(self.tasks_by_status.get(status, []))
                for status in [s.value for s in TaskStatus]
            }
        }

    def get_status_summary(self) -> Dict[str, int]:
        """
        获取状态摘要

        Returns:
            Dict[str, int]: 各状态任务数量
        """
        return {
            status: len(self.tasks_by_status.get(status.value, []))
            for status in TaskStatus
        }

    # ============================================================
    # 清理操作
    # ============================================================

    def cleanup_old_tasks(self, older_than_hours: int = 24) -> int:
        """
        清理旧任务记录

        Args:
            older_than_hours: 任务年龄限制（小时）

        Returns:
            int: 清理的任务数量
        """
        current_time = datetime.now()
        cleaned_count = 0

        # 清理已完成的任务
        tasks_to_remove = []
        for task_id, task_info in self.tasks.items():
            if task_info.completed_at:
                hours_diff = (current_time - task_info.completed_at).total_seconds() / 3600
                if hours_diff > older_than_hours:
                    tasks_to_remove.append(task_id)

        for task_id in tasks_to_remove:
            self.remove_task(task_id)
            cleaned_count += 1

        # 清理批量任务
        batches_to_remove = []
        for batch_id, batch_info in self.batch_tasks.items():
            if batch_info.created_at:
                hours_diff = (current_time - batch_info.created_at).total_seconds() / 3600
                if hours_diff > older_than_hours:
                    batches_to_remove.append(batch_id)

        for batch_id in batches_to_remove:
            del self.batch_tasks[batch_id]
            cleaned_count += 1

        if cleaned_count > 0:
            logger.info(f"清理了 {cleaned_count} 个旧任务记录")

        return cleaned_count

    def clear_all_tasks(self) -> int:
        """
        清除所有任务

        Returns:
            int: 清除的任务数量
        """
        count = len(self.tasks)
        self.tasks.clear()
        self.batch_tasks.clear()
        self.tasks_by_status.clear()

        logger.info(f"清除了所有任务记录: {count} 个")
        return count

    # ============================================================
    # 统计更新
    # ============================================================

    def record_success(self, processing_time: float, character_count: int = 0) -> None:
        """
        记录成功处理

        Args:
            processing_time: 处理时间（秒）
            character_count: 字符数
        """
        self.stats["total_processed"] += 1
        self.stats["total_success"] += 1
        self.stats["total_processing_time"] += processing_time
        self.stats["total_characters"] += character_count

    def record_failure(self) -> None:
        """记录处理失败"""
        self.stats["total_processed"] += 1
        self.stats["total_failed"] += 1

    def reset_statistics(self) -> None:
        """重置统计信息"""
        self.stats = {
            "total_processed": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_processing_time": 0.0,
            "total_characters": 0,
        }
        logger.info("统计信息已重置")
