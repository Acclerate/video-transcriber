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
    
    @patch('core.transcription_engine.process_video_url')
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
    
    @patch('core.transcription_engine.process_video_url')
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


class TestBatchTranscribeEndpoint:
    """批量转录端点测试"""
    
    def test_batch_transcribe_success(self, client):
        """测试批量转录成功"""
        request_data = {
            "urls": [
                "https://v.douyin.com/wrvKzCqdS5k/",
                "https://www.bilibili.com/video/BV1234567890"
            ],
            "options": {
                "model": "small",
                "language": "auto"
            },
            "max_concurrent": 2
        }
        
        response = client.post("/api/v1/batch-transcribe", json=request_data)
        assert response.status_code == 200
        
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "批量任务已创建"
        assert "data" in data
    
    def test_batch_transcribe_too_many_urls(self, client):
        """测试URL数量过多"""
        urls = [f"https://v.douyin.com/test{i}" for i in range(25)]
        
        request_data = {
            "urls": urls,
            "options": {
                "model": "small"
            }
        }
        
        response = client.post("/api/v1/batch-transcribe", json=request_data)
        assert response.status_code == 400
        assert "最多支持20个视频" in response.json()["detail"]
    
    def test_batch_transcribe_invalid_urls(self, client):
        """测试包含无效URL"""
        request_data = {
            "urls": [
                "https://v.douyin.com/wrvKzCqdS5k/",
                "invalid-url",
                "https://unsupported.com/video"
            ],
            "options": {
                "model": "small"
            }
        }
        
        response = client.post("/api/v1/batch-transcribe", json=request_data)
        assert response.status_code == 400
        assert "无效的视频链接" in response.json()["detail"]


class TestStatusEndpoints:
    """状态查询端点测试"""
    
    @patch('core.transcription_engine.get_task_status')
    def test_get_task_status_success(self, mock_get_status, client, sample_video_info, sample_transcription_result):
        """测试获取任务状态成功"""
        from models.schemas import TaskInfo, TaskStatus
        from datetime import datetime
        
        mock_task = TaskInfo(
            task_id="test_task_123",
            url="https://v.douyin.com/wrvKzCqdS5k/",
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