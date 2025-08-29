"""
视频转录核心引擎
整合视频解析、下载、音频提取和语音转录功能
"""

import asyncio
import uuid
import time
from datetime import datetime
from typing import List, Optional, Dict, Any, Callable
from pathlib import Path

from loguru import logger

from models.schemas import (
    VideoInfo, TranscriptionResult, TaskInfo, BatchTaskInfo,
    TaskStatus, ProcessOptions, WhisperModel, Language, OutputFormat
)
from .parser import video_parser
from .downloader import video_downloader, download_video_and_extract_audio
from .transcriber import speech_transcriber


class VideoTranscriptionEngine:
    """视频转录核心引擎"""
    
    def __init__(self, temp_dir: str = "./temp"):
        """
        初始化引擎
        
        Args:
            temp_dir: 临时文件目录
        """
        self.temp_dir = Path(temp_dir)
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # 任务管理
        self.tasks: Dict[str, TaskInfo] = {}
        self.batch_tasks: Dict[str, BatchTaskInfo] = {}
        
        # 统计信息
        self.stats = {
            "total_processed": 0,
            "total_success": 0,
            "total_failed": 0,
            "total_processing_time": 0.0
        }
    
    async def process_video_url(
        self,
        url: str,
        options: ProcessOptions,
        progress_callback: Optional[Callable[[str, float, str], None]] = None
    ) -> TranscriptionResult:
        """
        处理单个视频URL
        
        Args:
            url: 视频链接
            options: 处理选项
            progress_callback: 进度回调 (task_id, progress, message)
            
        Returns:
            TranscriptionResult: 转录结果
        """
        task_id = self._generate_task_id()
        task_info = None
        
        try:
            logger.info(f"开始处理视频: {url}")
            start_time = time.time()
            
            # 创建任务记录
            task_info = TaskInfo(
                task_id=task_id,
                url=url,
                status=TaskStatus.PENDING,
                progress=0,
                started_at=datetime.now(),
                completed_at=None,
                error_message=None,
                video_info=None,
                result=None
            )
            self.tasks[task_id] = task_info
            
            # 进度回调包装
            def update_progress(progress: float, message: str = ""):
                task_info.progress = int(progress)
                if progress_callback:
                    progress_callback(task_id, progress, message)
            
            # 1. 解析视频链接
            update_progress(10, "正在解析视频链接...")
            task_info.status = TaskStatus.DOWNLOADING
            
            video_info = await video_parser.get_video_info(url)
            task_info.video_info = video_info
            
            logger.info(f"视频解析成功: {video_info.title}")
            update_progress(20, f"解析成功: {video_info.title}")
            
            # 2. 下载视频并提取音频
            def download_progress(progress: float):
                # 下载进度占20-60%
                total_progress = 20 + (progress * 0.4)
                update_progress(total_progress, "正在下载视频...")
            
            audio_path = await download_video_and_extract_audio(
                video_info=video_info,
                audio_format="wav",
                optimize=True,
                progress_callback=download_progress
            )
            
            logger.info(f"音频提取成功: {audio_path}")
            update_progress(60, "音频提取完成")
            
            # 3. 语音转录
            task_info.status = TaskStatus.TRANSCRIBING
            
            def transcribe_progress(progress: float):
                # 转录进度占60-95%
                total_progress = 60 + (progress * 0.35)
                update_progress(total_progress, "正在进行语音识别...")
            
            # 设置转录器模型
            if speech_transcriber.model_name != options.model:
                speech_transcriber.model_name = options.model
                speech_transcriber.model = None  # 强制重新加载
            
            transcription_result = await speech_transcriber.transcribe_audio(
                audio_path=audio_path,
                language=options.language,
                with_timestamps=options.with_timestamps,
                temperature=options.temperature,
                progress_callback=transcribe_progress
            )
            
            logger.info(f"转录完成: {len(transcription_result.text)} 字符")
            update_progress(95, "转录完成，正在处理结果...")
            
            # 4. 清理临时文件
            try:
                Path(audio_path).unlink()
            except Exception:
                pass
            
            # 5. 完成任务
            task_info.status = TaskStatus.COMPLETED
            task_info.result = transcription_result
            task_info.completed_at = datetime.now()
            
            processing_time = time.time() - start_time
            
            # 更新统计信息
            self.stats["total_processed"] += 1
            self.stats["total_success"] += 1
            self.stats["total_processing_time"] += processing_time
            
            update_progress(100, "处理完成")
            
            logger.info(f"视频处理完成，耗时: {processing_time:.2f}秒")
            return transcription_result
            
        except Exception as e:
            # 错误处理
            logger.error(f"视频处理失败: {e}")
            
            if task_info is not None:
                task_info.status = TaskStatus.FAILED
                task_info.error_message = str(e)
                task_info.completed_at = datetime.now()
            
            self.stats["total_processed"] += 1
            self.stats["total_failed"] += 1
            
            if progress_callback:
                progress_callback(task_id, 0, f"处理失败: {str(e)}")
            
            raise Exception(f"视频处理失败: {str(e)}")
    
    async def process_batch_urls(
        self,
        urls: List[str],
        options: ProcessOptions,
        max_concurrent: int = 3,
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]] = None
    ) -> BatchTaskInfo:
        """
        批量处理视频URL
        
        Args:
            urls: 视频链接列表
            options: 处理选项
            max_concurrent: 最大并发数
            progress_callback: 进度回调 (batch_id, status_info)
            
        Returns:
            BatchTaskInfo: 批量任务信息
        """
        batch_id = self._generate_batch_id()
        
        try:
            logger.info(f"开始批量处理 {len(urls)} 个视频")
            
            # 创建批量任务记录
            batch_info = BatchTaskInfo(
                batch_id=batch_id,
                total_count=len(urls),
                pending_count=len(urls),
                completed_count=0,
                failed_count=0
            )
            self.batch_tasks[batch_id] = batch_info
            
            # 创建信号量限制并发数
            semaphore = asyncio.Semaphore(max_concurrent)
            
            async def process_single_url(url: str) -> Optional[TranscriptionResult]:
                async with semaphore:
                    try:
                        def single_progress(task_id: str, progress: float, message: str):
                            # 更新批量任务进度
                            self._update_batch_progress(batch_id, progress_callback)
                        
                        result = await self.process_video_url(
                            url=url,
                            options=options,
                            progress_callback=single_progress
                        )
                        
                        # 更新批量任务统计
                        batch_info.completed_count += 1
                        batch_info.pending_count -= 1
                        
                        return result
                        
                    except Exception as e:
                        logger.error(f"URL处理失败: {url}, 错误: {e}")
                        
                        # 更新批量任务统计
                        batch_info.failed_count += 1
                        batch_info.pending_count -= 1
                        
                        return None
            
            # 并发执行处理任务
            tasks = [process_single_url(url) for url in urls]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            success_count = len([r for r in results if r is not None and not isinstance(r, Exception)])
            
            logger.info(f"批量处理完成，成功: {success_count}/{len(urls)}")
            
            # 最终进度回调
            if progress_callback:
                progress_callback(batch_id, {
                    "total": len(urls),
                    "completed": batch_info.completed_count,
                    "failed": batch_info.failed_count,
                    "success_rate": success_count / len(urls) if urls else 0
                })
            
            return batch_info
            
        except Exception as e:
            logger.error(f"批量处理失败: {e}")
            raise Exception(f"批量处理失败: {str(e)}")
    
    def _update_batch_progress(
        self, 
        batch_id: str, 
        progress_callback: Optional[Callable[[str, Dict[str, Any]], None]]
    ):
        """更新批量任务进度"""
        if batch_id in self.batch_tasks and progress_callback:
            batch_info = self.batch_tasks[batch_id]
            progress_callback(batch_id, {
                "total": batch_info.total_count,
                "completed": batch_info.completed_count,
                "failed": batch_info.failed_count,
                "pending": batch_info.pending_count
            })
    
    def get_task_status(self, task_id: str) -> Optional[TaskInfo]:
        """获取任务状态"""
        return self.tasks.get(task_id)
    
    def get_batch_status(self, batch_id: str) -> Optional[BatchTaskInfo]:
        """获取批量任务状态"""
        return self.batch_tasks.get(batch_id)
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            **self.stats,
            "active_tasks": len([t for t in self.tasks.values() 
                               if t.status in [TaskStatus.PENDING, TaskStatus.DOWNLOADING, 
                                             TaskStatus.EXTRACTING, TaskStatus.TRANSCRIBING]]),
            "total_tasks": len(self.tasks),
            "average_processing_time": (
                self.stats["total_processing_time"] / self.stats["total_processed"] 
                if self.stats["total_processed"] > 0 else 0
            )
        }
    
    def cleanup_old_tasks(self, older_than_hours: int = 24) -> int:
        """清理旧任务记录"""
        try:
            current_time = datetime.now()
            cleaned_count = 0
            
            # 清理单个任务
            tasks_to_remove = []
            for task_id, task_info in self.tasks.items():
                if task_info.completed_at:
                    hours_diff = (current_time - task_info.completed_at).total_seconds() / 3600
                    if hours_diff > older_than_hours:
                        tasks_to_remove.append(task_id)
            
            for task_id in tasks_to_remove:
                del self.tasks[task_id]
                cleaned_count += 1
            
            # 清理批量任务
            batches_to_remove = []
            for batch_id, batch_info in self.batch_tasks.items():
                hours_diff = (current_time - batch_info.created_at).total_seconds() / 3600
                if hours_diff > older_than_hours:
                    batches_to_remove.append(batch_id)
            
            for batch_id in batches_to_remove:
                del self.batch_tasks[batch_id]
                cleaned_count += 1
            
            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个旧任务记录")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"任务清理失败: {e}")
            return 0
    
    async def cleanup_temp_files(self) -> int:
        """清理临时文件"""
        return video_downloader.cleanup_files()
    
    def _generate_task_id(self) -> str:
        """生成任务ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8]
        return f"task_{timestamp}_{random_suffix}"
    
    def _generate_batch_id(self) -> str:
        """生成批量任务ID"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        random_suffix = uuid.uuid4().hex[:8]
        return f"batch_{timestamp}_{random_suffix}"


# 全局引擎实例
transcription_engine = VideoTranscriptionEngine()


async def transcribe_video_url(
    url: str,
    model: WhisperModel = WhisperModel.SMALL,
    language: Language = Language.AUTO,
    with_timestamps: bool = False,
    output_format: OutputFormat = OutputFormat.JSON,
    progress_callback: Optional[Callable[[str, float, str], None]] = None
) -> TranscriptionResult:
    """
    转录视频URL的便捷函数
    
    Args:
        url: 视频链接
        model: Whisper模型
        language: 语言
        with_timestamps: 是否包含时间戳
        output_format: 输出格式
        progress_callback: 进度回调
        
    Returns:
        TranscriptionResult: 转录结果
    """
    options = ProcessOptions(
        model=model,
        language=language,
        with_timestamps=with_timestamps,
        output_format=output_format,
        enable_gpu=True,
        temperature=0.0
    )
    
    return await transcription_engine.process_video_url(
        url=url,
        options=options,
        progress_callback=progress_callback
    )


if __name__ == "__main__":
    # 测试代码
    import asyncio
    
    async def test():
        engine = VideoTranscriptionEngine()
        
        try:
            print("测试引擎初始化...")
            print(f"统计信息: {engine.get_statistics()}")
            
            # 测试任务ID生成
            task_id = engine._generate_task_id()
            batch_id = engine._generate_batch_id()
            print(f"任务ID: {task_id}")
            print(f"批量ID: {batch_id}")
            
            # 测试清理
            cleaned_tasks = engine.cleanup_old_tasks(0)
            cleaned_files = await engine.cleanup_temp_files()
            print(f"清理任务: {cleaned_tasks}, 清理文件: {cleaned_files}")
            
        except Exception as e:
            print(f"测试失败: {e}")
    
    # asyncio.run(test())