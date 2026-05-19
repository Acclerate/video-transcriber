"""
引擎编排测试
用 mock 隔离外部依赖，测试 VideoTranscriptionEngine 的管理逻辑
"""

import pytest
from datetime import datetime, timedelta

from core.engine import VideoTranscriptionEngine
from models.schemas import TaskInfo, TaskStatus, BatchTaskInfo, ProcessOptions


class TestEngineInit:

    def test_creates_temp_dir(self, tmp_path):
        temp = tmp_path / "engine_temp"
        engine = VideoTranscriptionEngine(temp_dir=str(temp))
        assert temp.exists()

    def test_stats_initialized(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        assert engine.stats["total_processed"] == 0
        assert engine.stats["total_success"] == 0
        assert engine.stats["total_failed"] == 0

    def test_tasks_empty(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        assert len(engine.tasks) == 0
        assert len(engine.batch_tasks) == 0


class TestGetTaskStatus:

    def test_existing_task(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        task = TaskInfo(
            task_id="t1", file_path="/tmp/a.mp4",
            status=TaskStatus.EXTRACTING, progress=50,
        )
        engine.tasks["t1"] = task
        assert engine.get_task_status("t1") is task

    def test_nonexistent_task(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        assert engine.get_task_status("nonexistent") is None


class TestGetBatchStatus:

    def test_existing_batch(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        batch = BatchTaskInfo(
            batch_id="b1", total_count=1, pending_count=1,
        )
        engine.batch_tasks["b1"] = batch
        assert engine.get_batch_status("b1") is batch

    def test_nonexistent_batch(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        assert engine.get_batch_status("none") is None


class TestGetStatistics:

    def test_initial_statistics(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        stats = engine.get_statistics()
        assert stats["total_processed"] == 0
        assert "active_tasks" in stats

    def test_statistics_after_success(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        engine.stats["total_processed"] = 5
        engine.stats["total_success"] = 4
        engine.stats["total_failed"] = 1
        stats = engine.get_statistics()
        assert stats["total_processed"] == 5
        assert stats["total_success"] == 4


class TestCleanupOldTasks:

    def test_removes_old_tasks(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        old_time = datetime.now() - timedelta(hours=48)
        task = TaskInfo(
            task_id="old", file_path="/tmp/a.mp4",
            status=TaskStatus.COMPLETED, progress=100,
            created_at=old_time, completed_at=old_time,
        )
        engine.tasks["old"] = task
        engine.cleanup_old_tasks(older_than_hours=24)
        assert "old" not in engine.tasks

    def test_keeps_recent_tasks(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        recent_time = datetime.now() - timedelta(hours=1)
        task = TaskInfo(
            task_id="recent", file_path="/tmp/a.mp4",
            status=TaskStatus.COMPLETED, progress=100,
            created_at=recent_time, completed_at=recent_time,
        )
        engine.tasks["recent"] = task
        engine.cleanup_old_tasks(older_than_hours=24)
        assert "recent" in engine.tasks


class TestGenerateIds:

    def test_task_id_unique(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        ids = {engine._generate_task_id() for _ in range(100)}
        assert len(ids) == 100

    def test_batch_id_unique(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        ids = {engine._generate_batch_id() for _ in range(100)}
        assert len(ids) == 100

    def test_task_id_format(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        tid = engine._generate_task_id()
        assert isinstance(tid, str)
        assert len(tid) > 0

    def test_batch_id_format(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        bid = engine._generate_batch_id()
        assert isinstance(bid, str)
        assert len(bid) > 0


class TestProcessVideoUrl:

    @pytest.mark.asyncio
    async def test_raises_not_implemented(self, tmp_path):
        engine = VideoTranscriptionEngine(temp_dir=str(tmp_path))
        options = ProcessOptions()
        with pytest.raises(NotImplementedError):
            await engine.process_video_url("https://example.com/video.mp4", options)
