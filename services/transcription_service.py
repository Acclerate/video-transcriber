"""
转录服务
封装视频转录的业务逻辑
"""

import asyncio
import uuid
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any, Callable

from loguru import logger

from config import settings
from models.schemas import (
    TranscriptionResult, TaskInfo, TaskStatus,
    ProcessOptions, WhisperModel, Language, OutputFormat
)
from core.engine import VideoTranscriptionEngine
from core.downloader import AudioExtractor
from .file_service import FileService
from .task_service import TaskService


class TranscriptionService:
    """
    转录服务
    协调音频提取和语音转录的完整流程
    """

    def __init__(self, config: Optional[settings] = None):
        """
        初始化转录服务

        Args:
            config: 应用配置，默认使用全局配置
        """
        self.config = config or settings

        # 初始化组件
        self.engine = VideoTranscriptionEngine(
            temp_dir=self.config.TEMP_DIR
        )
        self.audio_extractor = AudioExtractor(
            temp_dir=self.config.TEMP_DIR,
            cleanup_after=self.config.CLEANUP_AFTER
        )
        self.file_service = FileService(self.config)
        self.task_service = TaskService(self.config)

        logger.info("转录服务初始化完成")

    async def transcribe_file(
        self,
        file_path: str,
        options: Optional[ProcessOptions] = None,
        progress_callback: Optional[Callable[[str, float, str], None]] = None
    ) -> TranscriptionResult:
        """
        转录单个视频文件

        Args:
            file_path: 视频文件路径
            options: 处理选项
            progress_callback: 进度回调函数 (task_id, progress, message)

        Returns:
            TranscriptionResult: 转录结果
        """
        # 使用默认选项
        if options is None:
            options = ProcessOptions(
                model=WhisperModel(self.config.DEFAULT_MODEL),
                language=Language(self.config.DEFAULT_LANGUAGE),
                with_timestamps=self.config.ENABLE_WORD_TIMESTAMPS,
                output_format=OutputFormat.TXT,
                enable_gpu=self.config.ENABLE_GPU,
                temperature=self.config.DEFAULT_TEMPERATURE
            )

        # 创建任务
        task_id = self._generate_task_id()
        task_info = TaskInfo(
            task_id=task_id,
            file_path=file_path,
            status=TaskStatus.PENDING,
            progress=0,
            started_at=datetime.now(),
            completed_at=None,
            error_message=None,
            video_info=None,
            result=None
        )
        self.task_service.add_task(task_id, task_info)

        try:
            logger.info(f"开始处理视频文件: {file_path}")

            # 验证文件
            await self._validate_file(file_path, task_id, progress_callback)

            # 获取视频信息
            video_info = self.audio_extractor.get_video_info(file_path)
            task_info.video_info = video_info

            # 提取音频
            audio_path = await self._extract_audio(
                file_path, task_id, progress_callback
            )

            # 执行转录
            result = await self._transcribe(
                audio_path, options, task_id, progress_callback
            )

            # 清理临时文件
            await self._cleanup_temp_files(audio_path)

            # 更新任务状态
            task_info.status = TaskStatus.COMPLETED
            task_info.result = result
            task_info.completed_at = datetime.now()
            task_info.progress = 100

            if progress_callback:
                progress_callback(task_id, 100, "处理完成")

            logger.info(f"视频处理完成: {file_path}")
            return result

        except Exception as e:
            logger.error(f"视频处理失败: {e}")
            task_info.status = TaskStatus.FAILED
            task_info.error_message = str(e)
            task_info.completed_at = datetime.now()

            if progress_callback:
                progress_callback(task_id, 0, f"处理失败: {str(e)}")

            raise Exception(f"视频处理失败: {str(e)}")

    async def transcribe_batch(
        self,
        file_paths: List[str],
        options: Optional[ProcessOptions] = None,
        max_concurrent: Optional[int] = None,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        批量转录视频文件

        Args:
            file_paths: 视频文件路径列表
            options: 处理选项
            max_concurrent: 最大并发数
            progress_callback: 进度回调函数 (batch_id, status_info)

        Returns:
            Dict[str, Any]: 批量处理结果统计
        """
        batch_id = self._generate_batch_id()

        if options is None:
            options = ProcessOptions(
                model=WhisperModel(self.config.DEFAULT_MODEL),
                language=Language(self.config.DEFAULT_LANGUAGE),
                with_timestamps=self.config.ENABLE_WORD_TIMESTAMPS,
                output_format=OutputFormat.TXT,
                enable_gpu=self.config.ENABLE_GPU,
                temperature=self.config.DEFAULT_TEMPERATURE
            )

        if max_concurrent is None:
            max_concurrent = self.config.MAX_CONCURRENT_TASKS

        logger.info(f"开始批量处理 {len(file_paths)} 个视频文件")

        # 创建信号量限制并发数
        semaphore = asyncio.Semaphore(max_concurrent)

        async def process_single(file_path: str) -> Optional[TranscriptionResult]:
            async with semaphore:
                try:
                    def single_progress(task_id: str, progress: float, message: str):
                        if progress_callback:
                            # 更新批量任务进度
                            self._update_batch_progress(batch_id, progress_callback)

                    return await self.transcribe_file(
                        file_path=file_path,
                        options=options,
                        progress_callback=single_progress
                    )
                except Exception as e:
                    logger.error(f"文件处理失败: {file_path}, 错误: {e}")
                    return None

        # 并发执行处理任务
        tasks = [process_single(path) for path in file_paths]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 统计结果
        success_count = sum(1 for r in results if r is not None and not isinstance(r, Exception))
        failed_count = len(results) - success_count

        batch_result = {
            "batch_id": batch_id,
            "total": len(file_paths),
            "success": success_count,
            "failed": failed_count,
            "success_rate": success_count / len(file_paths) if file_paths else 0
        }

        logger.info(f"批量处理完成: {success_count}/{len(file_paths)} 成功")

        if progress_callback:
            progress_callback(batch_id, batch_result)

        return batch_result

    async def transcribe_from_url(
        self,
        url: str,
        options: Optional[ProcessOptions] = None,
        progress_callback: Optional[Callable[[str, float, str], None]] = None
    ) -> TranscriptionResult:
        """
        从 URL 转录视频

        Args:
            url: 视频 URL
            options: 处理选项
            progress_callback: 进度回调函数

        Returns:
            TranscriptionResult: 转录结果
        """
        # 下载视频
        downloaded_path = await self.file_service.download_from_url(
            url,
            progress_callback=progress_callback
        )

        # 转录下载的文件
        result = await self.transcribe_file(
            file_path=downloaded_path,
            options=options,
            progress_callback=progress_callback
        )

        # 清理下载的文件
        try:
            Path(downloaded_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"清理下载文件失败: {e}")

        return result

    # ============================================================
    # 私有方法
    # ============================================================

    async def _validate_file(
        self,
        file_path: str,
        task_id: str,
        progress_callback: Optional[Callable[[str, float, str], None]]
    ) -> None:
        """验证文件"""
        if progress_callback:
            progress_callback(task_id, 5, "正在验证文件...")

        # 检查文件是否存在
        path = Path(file_path)
        if not path.exists():
            raise Exception(f"文件不存在: {file_path}")

        # 检查文件大小
        file_size = path.stat().st_size
        max_size = self.config.MAX_FILE_SIZE * 1024 * 1024  # MB to bytes
        if file_size > max_size:
            raise Exception(
                f"文件大小超过限制 ({self.config.MAX_FILE_SIZE}MB)"
            )

        # 检查文件格式
        if not self.file_service.is_supported_video_file(file_path):
            raise Exception(f"不支持的视频格式: {path.suffix}")

    async def _extract_audio(
        self,
        video_path: str,
        task_id: str,
        progress_callback: Optional[Callable[[str, float, str], None]]
    ) -> str:
        """提取音频"""
        def update_progress(progress: float):
            if progress_callback:
                # 音频提取占 10-50%
                total_progress = 10 + (progress * 0.4)
                progress_callback(task_id, total_progress, "正在提取音频...")

        audio_path = await self.audio_extractor.extract_and_optimize(
            video_path=video_path,
            optimize=True,
            progress_callback=update_progress
        )

        if progress_callback:
            progress_callback(task_id, 50, "音频提取完成")

        return audio_path

    async def _transcribe(
        self,
        audio_path: str,
        options: ProcessOptions,
        task_id: str,
        progress_callback: Optional[Callable[[str, float, str], None]]
    ) -> TranscriptionResult:
        """执行转录"""
        from core.transcriber import speech_transcriber

        # 设置模型
        if speech_transcriber.model_name != options.model:
            speech_transcriber.model_name = options.model
            speech_transcriber.model = None

        def update_progress(progress: float):
            if progress_callback:
                # 转录占 50-95%
                total_progress = 50 + (progress * 0.45)
                progress_callback(task_id, total_progress, "正在进行语音识别...")

        result = await speech_transcriber.transcribe_audio(
            audio_path=audio_path,
            language=options.language,
            with_timestamps=options.with_timestamps,
            temperature=options.temperature,
            progress_callback=update_progress
        )

        if progress_callback:
            progress_callback(task_id, 95, "转录完成")

        return result

    async def _cleanup_temp_files(self, audio_path: str) -> None:
        """清理临时文件"""
        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning(f"清理临时文件失败: {e}")

    def _update_batch_progress(
        self,
        batch_id: str,
        progress_callback: Callable[[str, Dict[str, Any]], None]
    ) -> None:
        """更新批量任务进度"""
        stats = self.task_service.get_statistics()
        progress_callback(batch_id, {
            "total": stats.get("total_tasks", 0),
            "completed": stats.get("total_success", 0),
            "failed": stats.get("total_failed", 0),
            "pending": stats.get("active_tasks", 0)
        })

    def _generate_task_id(self) -> str:
        """生成任务 ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8]
        return f"task_{timestamp}_{random_suffix}"

    def _generate_batch_id(self) -> str:
        """生成批量任务 ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8]
        return f"batch_{timestamp}_{random_suffix}"

    # ============================================================
    # 公共方法
    # ============================================================

    def get_task_status(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务状态"""
        return self.task_service.get_task(task_id)

    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return self.task_service.get_statistics()

    async def cleanup_old_tasks(self, older_than_hours: int = 24) -> int:
        """清理旧任务"""
        return self.task_service.cleanup_old_tasks(older_than_hours)

    async def cleanup_temp_files(self) -> int:
        """清理临时文件"""
        return self.audio_extractor.cleanup_files()
