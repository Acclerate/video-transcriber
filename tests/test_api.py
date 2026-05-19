"""
测试API接口
"""

import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from api.apimain import app
from models.schemas import TranscriptionModel, Language


@pytest.fixture
def client():
    """测试客户端"""
    return TestClient(app)


class TestHealthEndpoint:
    """健康检查端点测试"""

    def test_health_check(self, client):
        """测试健康检查"""
        response = client.get("/health")
        assert response.status_code == 200

        data = response.json()
        assert data["status"] in ("healthy", "degraded")
        assert "version" in data
        assert "components" in data


class TestRootEndpoint:
    """根端点测试"""

    def test_root_endpoint(self, client):
        """测试根端点"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestTranscribeEndpoint:
    """转录端点测试"""

    def test_transcribe_file_no_file(self, client):
        """测试缺少文件上传"""
        response = client.post("/api/v1/transcribe/file")
        assert response.status_code == 422  # Validation error

    @pytest.mark.asyncio
    async def test_transcribe_url_not_implemented(self):
        """测试 URL 转录功能未实现时返回错误消息"""
        import json
        from api.websocket import handle_transcribe_request
        from unittest.mock import AsyncMock

        ws = AsyncMock()
        await handle_transcribe_request(ws, {"url": "https://example.com/video.mp4"})

        ws.send_text.assert_called()
        sent_json = ws.send_text.call_args[0][0]
        sent_data = json.loads(sent_json)
        assert sent_data["type"] == "error"


class TestBatchTranscribeEndpoint:
    """批量转录端点测试"""

    def test_batch_transcribe_max_concurrent_validation(self, client):
        """测试并发数验证"""
        from io import BytesIO

        file1 = BytesIO(b"fake video content")

        response = client.post(
            "/api/v1/transcribe/batch",
            files={"files": ("video1.mp4", file1, "video/mp4")},
            data={
                "model": "small",
                "max_concurrent": "15"  # 超过最大值10
            }
        )

        assert response.status_code == 400
        assert "max_concurrent" in response.json()["detail"]

    def test_batch_transcribe_too_many_files(self, client):
        """测试文件数量过多"""
        from io import BytesIO

        files = []
        for i in range(25):
            files.append(("files", (f"video{i}.mp4", BytesIO(b"fake content"), "video/mp4")))

        response = client.post(
            "/api/v1/transcribe/batch",
            files=files,
            data={"model": "small"}
        )

        assert response.status_code == 400
        assert "最多支持20个文件" in response.json()["detail"]


class TestStatusEndpoints:
    """状态查询端点测试"""

    @patch('api.routes.tasks._transcription_service.get_task_status')
    def test_get_task_status_success(self, mock_get_status, client, sample_video_info, sample_transcription_result):
        """测试获取任务状态成功"""
        from models.schemas import TaskInfo, TaskStatus
        from datetime import datetime

        mock_task = TaskInfo(
            task_id="test_task_123",
            file_path="/path/to/video.mp4",
            status=TaskStatus.COMPLETED,
            progress=100,
            media_info=sample_video_info,
            result=sample_transcription_result,
            started_at=datetime.now(),
            completed_at=datetime.now(),
            error_message=None
        )
        mock_get_status.return_value = mock_task

        response = client.get("/api/v1/status/test_task_123")
        assert response.status_code == 200

        data = response.json()
        assert data["code"] == 200
        assert data["data"]["task_id"] == "test_task_123"
        assert data["data"]["status"] == "completed"

    @patch('api.routes.tasks._transcription_service.get_task_status')
    def test_get_task_status_not_found(self, mock_get_status, client):
        """测试任务不存在"""
        mock_get_status.return_value = None

        response = client.get("/api/v1/status/nonexistent_task")
        assert response.status_code == 404
        assert response.json()["code"] == 404


class TestModelsEndpoint:
    """模型信息端点测试"""

    def test_get_models(self, client):
        """测试获取模型信息"""
        response = client.get("/api/v1/models")
        assert response.status_code == 200

        data = response.json()
        assert data["code"] == 200
        assert "available_models" in data["data"]
        assert "current_model" in data["data"]
        assert "sensevoice-small" in data["data"]["available_models"]


class TestStatsEndpoint:
    """统计信息端点测试"""

    @patch('api.routes.transcribe._transcription_service.get_statistics')
    def test_get_stats(self, mock_get_stats, client):
        """测试获取统计信息"""
        mock_stats = {
            "total_processed": 10,
            "total_success": 8,
            "total_failed": 2,
            "active_tasks": 1,
            "average_processing_time": 15.5
        }
        mock_get_stats.return_value = mock_stats

        response = client.get("/api/v1/transcribe/stats")
        assert response.status_code == 200

        data = response.json()
        assert data["code"] == 200


class TestErrorHandling:
    """错误处理测试"""

    def test_404_error(self, client):
        """测试404错误"""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
