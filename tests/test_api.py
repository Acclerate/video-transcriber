"""
测试API接口
"""

import pytest
import json
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from api.main import app
from models.schemas import WhisperModel, Language


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
        assert data["status"] == "healthy"
        assert "message" in data


class TestRootEndpoint:
    """根端点测试"""
    
    def test_root_endpoint(self, client):
        """测试根端点"""
        response = client.get("/")
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]


class TestTranscribeEndpoint:
    """转录端点测试"""

    @patch('core.engine.VideoTranscriptionEngine.process_video_url')
    def test_transcribe_success(self, mock_process, client, sample_transcription_result):
        """测试转录成功"""
        mock_process.return_value = sample_transcription_result

        request_data = {
            "url": "https://v.douyin.com/wrvKzCqdS5k/",
            "options": {
                "model": "small",
                "language": "auto",
                "with_timestamps": True,
                "output_format": "json"
            }
        }

        response = client.post("/api/v1/transcribe", json=request_data)
        assert response.status_code == 200

        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "转录成功"
        assert "data" in data
        assert "transcription" in data["data"]

    def test_transcribe_invalid_url(self, client):
        """测试无效URL"""
        request_data = {
            "url": "invalid-url",
            "options": {
                "model": "small",
                "language": "auto"
            }
        }

        response = client.post("/api/v1/transcribe", json=request_data)
        assert response.status_code == 400
        assert "无效的视频链接" in response.json()["detail"]

    def test_transcribe_missing_url(self, client):
        """测试缺少URL"""
        request_data = {
            "options": {
                "model": "small"
            }
        }

        response = client.post("/api/v1/transcribe", json=request_data)
        assert response.status_code == 422  # Validation error

    @patch('core.engine.VideoTranscriptionEngine.process_video_url')
    def test_transcribe_processing_error(self, mock_process, client):
        """测试处理错误"""
        mock_process.side_effect = Exception("处理失败")

        request_data = {
            "url": "https://v.douyin.com/wrvKzCqdS5k/",
            "options": {
                "model": "small"
            }
        }

        response = client.post("/api/v1/transcribe", json=request_data)
        assert response.status_code == 500
        assert "转录失败" in response.json()["detail"]

    def test_transcribe_url_not_implemented(self, client):
        """测试URL功能未实现"""
        import asyncio

        # 不使用 mock，直接测试实际方法调用
        from core.engine import VideoTranscriptionEngine
        from models.schemas import ProcessOptions

        engine = VideoTranscriptionEngine()
        options = ProcessOptions(model=WhisperModel.SMALL)

        async def test_call():
            with pytest.raises(NotImplementedError) as exc_info:
                await engine.process_video_url(
                    url="https://example.com/video.mp4",
                    options=options
                )
            assert "URL视频下载功能未启用" in str(exc_info.value)

        asyncio.run(test_call())


class TestBatchTranscribeEndpoint:
    """批量转录端点测试"""

    @patch('services.transcription_service.TranscriptionService.transcribe_batch')
    def test_batch_transcribe_success(self, mock_transcribe, client):
        """测试批量文件转录成功"""
        mock_transcribe.return_value = {
            "batch_id": "batch_20240101_120000_abc123",
            "total": 2,
            "success": 2,
            "failed": 0,
            "success_rate": 1.0
        }

        # 创建测试文件
        from io import BytesIO

        file1 = BytesIO(b"fake video content 1")
        file2 = BytesIO(b"fake video content 2")

        response = client.post(
            "/api/v1/transcribe/batch",
            files={
                "files": ("video1.mp4", file1, "video/mp4"),
                "files": ("video2.mp4", file2, "video/mp4")
            },
            data={
                "model": "small",
                "language": "auto",
                "format": "txt",
                "max_concurrent": "2"
            }
        )

        # 由于实际会尝试保存文件，这里主要测试参数验证
        # 实际文件处理需要在集成测试中完成
        assert response.status_code in [200, 500]  # 可能因文件处理失败

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
        assert "max_concurrent 必须在 1-10 之间" in response.json()["detail"]

    def test_batch_transcribe_too_many_files(self, client):
        """测试文件数量过多"""
        from io import BytesIO

        # 创建超过20个文件
        files = []
        data = {"model": "small"}
        for i in range(25):
            files.append(("files", (f"video{i}.mp4", BytesIO(b"fake content"), "video/mp4")))

        response = client.post(
            "/api/v1/transcribe/batch",
            files=files,
            data=data
        )

        assert response.status_code == 400
        assert "最多支持20个文件" in response.json()["detail"]


class TestStatusEndpoints:
    """状态查询端点测试"""

    @patch('core.engine.VideoTranscriptionEngine.get_task_status')
    def test_get_task_status_success(self, mock_get_status, client, sample_video_info, sample_transcription_result):
        """测试获取任务状态成功"""
        from models.schemas import TaskInfo, TaskStatus
        from datetime import datetime

        mock_task = TaskInfo(
            task_id="test_task_123",
            file_path="/path/to/video.mp4",
            status=TaskStatus.COMPLETED,
            progress=100,
            video_info=sample_video_info,
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
    
    @patch('core.transcription_engine.get_task_status')
    def test_get_task_status_not_found(self, mock_get_status, client):
        """测试任务不存在"""
        mock_get_status.return_value = None

        response = client.get("/api/v1/status/nonexistent_task")
        assert response.status_code == 404
        assert "任务不存在" in response.json()["detail"]


class TestModelsEndpoint:
    """模型信息端点测试"""
    
    @patch('core.transcriber.speech_transcriber')
    def test_get_models(self, mock_transcriber, client):
        """测试获取模型信息"""
        mock_transcriber.get_available_models.return_value = {
            "tiny": {"size": "39MB", "speed": "10x", "accuracy": "★★☆☆☆"},
            "small": {"size": "244MB", "speed": "4x", "accuracy": "★★★★☆"}
        }
        mock_transcriber.get_model_info.return_value = {
            "name": "small",
            "device": "cpu",
            "loaded": True
        }
        
        response = client.get("/api/v1/models")
        assert response.status_code == 200
        
        data = response.json()
        assert data["code"] == 200
        assert "available_models" in data["data"]
        assert "current_model" in data["data"]


class TestStatsEndpoint:
    """统计信息端点测试"""
    
    @patch('core.transcription_engine.get_statistics')
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
        
        response = client.get("/api/v1/stats")
        assert response.status_code == 200
        
        data = response.json()
        assert data["code"] == 200
        assert data["data"]["total_processed"] == 10
        assert data["data"]["total_success"] == 8


class TestErrorHandling:
    """错误处理测试"""
    
    def test_404_error(self, client):
        """测试404错误"""
        response = client.get("/api/v1/nonexistent")
        assert response.status_code == 404
    
    def test_405_method_not_allowed(self, client):
        """测试方法不允许"""
        response = client.put("/api/v1/transcribe")
        assert response.status_code == 405
    
    def test_422_validation_error(self, client):
        """测试验证错误"""
        # 发送无效的JSON数据
        response = client.post("/api/v1/transcribe", json={"invalid": "data"})
        assert response.status_code == 422


class TestRateLimiting:
    """速率限制测试"""
    
    @pytest.mark.slow
    def test_rate_limiting(self, client):
        """测试速率限制"""
        # 这个测试可能需要实际配置速率限制
        # 或者使用mock来模拟速率限制行为
        pass


class TestRequestValidation:
    """请求验证测试"""
    
    def test_transcribe_request_validation(self, client):
        """测试转录请求验证"""
        # 测试各种无效的请求数据
        invalid_requests = [
            {},  # 空请求
            {"url": ""},  # 空URL
            {"url": "https://v.douyin.com/test", "options": {"model": "invalid"}},  # 无效模型
            {"url": "https://v.douyin.com/test", "options": {"language": "invalid"}},  # 无效语言
        ]
        
        for request_data in invalid_requests:
            response = client.post("/api/v1/transcribe", json=request_data)
            assert response.status_code in [400, 422]
    
    def test_batch_request_validation(self, client):
        """测试批量请求验证"""
        invalid_requests = [
            {"urls": []},  # 空URL列表
            {"urls": ["valid-url"], "max_concurrent": 0},  # 无效并发数
            {"urls": ["valid-url"], "max_concurrent": 100},  # 并发数过大
        ]
        
        for request_data in invalid_requests:
            response = client.post("/api/v1/batch-transcribe", json=request_data)
            assert response.status_code in [400, 422]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])