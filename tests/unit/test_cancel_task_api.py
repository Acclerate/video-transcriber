"""终止任务 API 测试。"""

from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from api.main import app


client = TestClient(app)


def test_cancel_task_success():
    """终止任务成功。"""
    with patch("api.routes.transcribe._transcription_service.cancel_task", new=AsyncMock(return_value={
        "success": True,
        "reason": "cancel_requested",
        "message": "已发送终止请求"
    })):
        response = client.post("/api/v1/transcribe/task/task_123/cancel")

    assert response.status_code == 200
    payload = response.json()
    assert payload["code"] == 200
    assert payload["data"]["task_id"] == "task_123"


def test_cancel_task_not_found():
    """任务不存在返回 404。"""
    with patch("api.routes.transcribe._transcription_service.cancel_task", new=AsyncMock(return_value={
        "success": False,
        "reason": "not_found",
        "message": "任务不存在"
    })):
        response = client.post("/api/v1/transcribe/task/none/cancel")

    assert response.status_code == 404
    assert "任务不存在" in response.json()["detail"]


def test_cancel_task_not_active():
    """任务不可终止返回 409。"""
    with patch("api.routes.transcribe._transcription_service.cancel_task", new=AsyncMock(return_value={
        "success": False,
        "reason": "not_active",
        "message": "任务当前状态为 completed，无法终止"
    })):
        response = client.post("/api/v1/transcribe/task/task_done/cancel")

    assert response.status_code == 409
    assert "无法终止" in response.json()["detail"]
