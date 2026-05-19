"""
服务层测试
FileService 和 TaskService 的纯逻辑 + mock 测试
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import Mock
from pathlib import Path

from models.schemas import TaskStatus, TaskInfo


# ============================================================
# FileService
# ============================================================

def _make_file_service(video_formats=None, audio_formats=None, max_file_size=500):
    from services.file_service import FileService
    service = FileService.__new__(FileService)
    service.config = Mock()
    service.config.VIDEO_FORMATS = video_formats or [".mp4", ".avi", ".mkv", ".mov"]
    service.config.AUDIO_FORMATS = audio_formats or [".mp3", ".wav", ".flac", ".aac"]
    service.config.MAX_FILE_SIZE = max_file_size
    return service


class TestFileServiceSupportedFormats:

    def test_video_mp4(self):
        fs = _make_file_service()
        assert fs.is_supported_video_file(Path("test.mp4")) is True

    def test_video_unsupported(self):
        fs = _make_file_service()
        assert fs.is_supported_video_file(Path("test.txt")) is False

    def test_audio_wav(self):
        fs = _make_file_service()
        assert fs.is_supported_audio_file(Path("test.wav")) is True

    def test_audio_unsupported(self):
        fs = _make_file_service()
        assert fs.is_supported_audio_file(Path("test.txt")) is False

    def test_media_file_video(self):
        fs = _make_file_service()
        assert fs.is_supported_media_file(Path("test.mp4")) is True

    def test_media_file_audio(self):
        fs = _make_file_service()
        assert fs.is_supported_media_file(Path("test.mp3")) is True

    def test_media_file_unsupported(self):
        fs = _make_file_service()
        assert fs.is_supported_media_file(Path("test.txt")) is False

    def test_case_insensitive(self):
        fs = _make_file_service()
        assert fs.is_supported_video_file(Path("test.MP4")) is True
        assert fs.is_supported_audio_file(Path("test.WAV")) is True


class TestFileServiceGetSafeFilename:

    def test_removes_special_chars(self):
        fs = _make_file_service()
        result = fs.get_safe_filename('file<>:"/\\|?*.mp4')
        assert "<" not in result
        assert ">" not in result
        assert ":" not in result

    def test_preserves_normal_name(self):
        fs = _make_file_service()
        result = fs.get_safe_filename("normal_file.mp4")
        assert result == "normal_file.mp4"

    def test_truncates_long_name(self):
        fs = _make_file_service()
        result = fs.get_safe_filename("a" * 300 + ".mp4", max_length=50)
        assert len(result) <= 50

    def test_chinese_filename(self):
        fs = _make_file_service()
        result = fs.get_safe_filename("中文文件名.mp4")
        assert "中文文件名" in result


class TestFileServiceValidateFile:

    @pytest.mark.asyncio
    async def test_nonexistent_file(self, tmp_path):
        fs = _make_file_service()
        valid, error = await fs.validate_file(tmp_path / "nonexistent.mp4")
        assert valid is False

    @pytest.mark.asyncio
    async def test_unsupported_format(self, tmp_path):
        fs = _make_file_service()
        test_file = tmp_path / "test.xyz"
        test_file.write_text("data")
        valid, error = await fs.validate_file(test_file)
        assert valid is False


# ============================================================
# TaskService
# ============================================================

def _make_task_service():
    from services.task_service import TaskService
    return TaskService()


class TestTaskServiceCRUD:

    def test_add_and_get(self):
        ts = _make_task_service()
        task = TaskInfo(
            task_id="t1", file_path="/tmp/a.mp4",
            status=TaskStatus.PENDING, progress=0,
        )
        ts.add_task("t1", task)
        assert ts.get_task("t1") is task

    def test_get_nonexistent(self):
        ts = _make_task_service()
        assert ts.get_task("none") is None

    def test_remove_task(self):
        ts = _make_task_service()
        task = TaskInfo(
            task_id="t1", file_path="/tmp/a.mp4",
            status=TaskStatus.COMPLETED, progress=100,
        )
        ts.add_task("t1", task)
        ts.remove_task("t1")
        assert ts.get_task("t1") is None

    def test_remove_nonexistent_no_error(self):
        ts = _make_task_service()
        ts.remove_task("nonexistent")  # should not raise


class TestTaskServiceUpdateStatus:

    def test_update_status(self):
        ts = _make_task_service()
        task = TaskInfo(
            task_id="t1", file_path="/tmp/a.mp4",
            status=TaskStatus.PENDING, progress=0,
        )
        ts.add_task("t1", task)
        ts.update_task_status("t1", TaskStatus.EXTRACTING, progress=50)
        updated = ts.get_task("t1")
        assert updated.status == TaskStatus.EXTRACTING
        assert updated.progress == 50


class TestTaskServiceStatistics:

    def test_initial_statistics(self):
        ts = _make_task_service()
        stats = ts.get_statistics()
        assert stats["total_processed"] == 0
        assert stats["total_success"] == 0
        assert stats["total_failed"] == 0

    def test_after_success(self):
        ts = _make_task_service()
        ts.record_success(10.0)
        stats = ts.get_statistics()
        assert stats["total_processed"] == 1
        assert stats["total_success"] == 1
        assert stats["average_processing_time"] == 10.0

    def test_after_failure(self):
        ts = _make_task_service()
        ts.record_failure()
        stats = ts.get_statistics()
        assert stats["total_processed"] == 1
        assert stats["total_failed"] == 1

    def test_multiple_operations(self):
        ts = _make_task_service()
        ts.record_success(5.0)
        ts.record_success(15.0)
        ts.record_failure()
        stats = ts.get_statistics()
        assert stats["total_processed"] == 3
        assert stats["total_success"] == 2
        assert stats["total_failed"] == 1
        # average = total_processing_time / total_processed
        assert stats["average_processing_time"] == pytest.approx(20.0 / 3)

    def test_reset_statistics(self):
        ts = _make_task_service()
        ts.record_success(5.0)
        ts.reset_statistics()
        stats = ts.get_statistics()
        assert stats["total_processed"] == 0


class TestTaskServiceCleanup:

    def test_cleanup_old_tasks(self):
        ts = _make_task_service()
        old_time = datetime.now() - timedelta(hours=48)
        task = TaskInfo(
            task_id="old", file_path="/tmp/a.mp4",
            status=TaskStatus.COMPLETED, progress=100,
            created_at=old_time, completed_at=old_time,
        )
        ts.add_task("old", task)
        ts.cleanup_old_tasks(older_than_hours=24)
        assert ts.get_task("old") is None

    def test_cleanup_keeps_recent(self):
        ts = _make_task_service()
        recent_time = datetime.now() - timedelta(hours=1)
        task = TaskInfo(
            task_id="recent", file_path="/tmp/a.mp4",
            status=TaskStatus.COMPLETED, progress=100,
            created_at=recent_time, completed_at=recent_time,
        )
        ts.add_task("recent", task)
        ts.cleanup_old_tasks(older_than_hours=24)
        assert ts.get_task("recent") is not None


class TestTaskServiceStatusSummary:

    def test_empty_summary(self):
        ts = _make_task_service()
        summary = ts.get_status_summary()
        for status in TaskStatus:
            assert summary.get(status) == 0

    def test_summary_after_tasks(self):
        ts = _make_task_service()
        t1 = TaskInfo(task_id="1", file_path="/a", status=TaskStatus.COMPLETED, progress=100)
        t2 = TaskInfo(task_id="2", file_path="/b", status=TaskStatus.EXTRACTING, progress=50)
        ts.add_task("1", t1)
        ts.add_task("2", t2)
        summary = ts.get_status_summary()
        assert summary[TaskStatus.COMPLETED] == 1
        assert summary[TaskStatus.EXTRACTING] == 1
