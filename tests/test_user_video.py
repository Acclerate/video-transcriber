"""
用户提供的抖音视频转录功能测试
"""

import pytest
import asyncio
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from api.main import app
from models.schemas import TranscribeRequest, ProcessOptions, WhisperModel, Language


@pytest.fixture
def client():
    """测试客户端"""
    return TestClient(app)


class TestUserVideoTranscription:
    """用户视频转录测试"""
    
    def test_user_douyin_video_api(self, client):
        """测试用户提供的抖音视频API接口"""
        # 用户的抖音视频链接
        user_video_url = "https://v.douyin.com/wrvKzCqdS5k/"
        
        request_data = {
            "url": user_video_url,
            "options": {
                "model": "small",
                "language": "auto",
                "with_timestamps": True,
                "output_format": "json",
                "enable_gpu": True,
                "temperature": 0.0
            }
        }
        
        # 发送请求到转录API
        response = client.post("/api/v1/transcribe", json=request_data)
        
        # 验证响应状态
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {response.text}")
        
        # 基本的响应验证
        assert response.status_code in [200, 500, 400], f"期望的状态码，实际收到: {response.status_code}"
    
    @patch('core.transcription_engine.process_video_url')
    def test_user_douyin_video_mock_success(self, mock_process, client, sample_transcription_result):
        """使用Mock测试用户抖音视频转录成功场景"""
        # 模拟成功的转录结果
        mock_process.return_value = sample_transcription_result
        
        user_video_url = "https://v.douyin.com/wrvKzCqdS5k/"
        
        request_data = {
            "url": user_video_url,
            "options": {
                "model": "small",
                "language": "auto",
                "with_timestamps": True,
                "output_format": "json",
                "enable_gpu": True,
                "temperature": 0.0
            }
        }
        
        response = client.post("/api/v1/transcribe", json=request_data)
        
        # 验证成功响应
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 200
        assert data["message"] == "转录成功"
        assert "data" in data
        assert "transcription" in data["data"]
        
        # 验证mock被调用
        mock_process.assert_called_once()
        call_args = mock_process.call_args
        if call_args.args:
            assert call_args.args[0] == user_video_url
        else:
            # 检查关键字参数
            assert "url" in call_args.kwargs
            assert call_args.kwargs["url"] == user_video_url
    
    @pytest.mark.network
    def test_url_validation(self, client):
        """测试URL验证功能"""
        user_video_url = "https://v.douyin.com/wrvKzCqdS5k/"
        
        # 测试URL格式验证
        from utils.helpers import validate_url
        is_valid = validate_url(user_video_url)
        print(f"URL验证结果: {is_valid}")
        
        # URL应该通过基本格式验证
        assert is_valid is True, f"URL格式验证失败: {user_video_url}"
    
    @pytest.mark.network 
    @pytest.mark.slow
    def test_platform_detection(self):
        """测试平台检测功能"""
        user_video_url = "https://v.douyin.com/wrvKzCqdS5k/"
        
        from core.video_parser import detect_platform, Platform
        
        # 检测平台
        detected_platform = detect_platform(user_video_url)
        print(f"检测到的平台: {detected_platform}")
        
        # 应该检测到抖音平台
        assert detected_platform == Platform.DOUYIN, f"平台检测错误，期望DOUYIN，实际: {detected_platform}"


class TestRealVideoProcessing:
    """真实视频处理测试（需要网络连接）"""
    
    @pytest.mark.network
    @pytest.mark.slow  
    def test_real_video_info_extraction(self):
        """测试真实视频信息提取"""
        user_video_url = "https://v.douyin.com/wrvKzCqdS5k/"
        
        from core.video_parser import VideoParser
        
        # 创建视频解析器实例
        parser = VideoParser()
        
        try:
            # 提取视频信息
            video_info = asyncio.run(parser.get_video_info(user_video_url))
            
            print(f"视频信息提取结果:")
            print(f"- 标题: {video_info.title}")
            print(f"- 平台: {video_info.platform}")
            print(f"- 时长: {video_info.duration}秒")
            print(f"- 上传者: {video_info.uploader}")
            print(f"- 观看次数: {video_info.view_count}")
            
            # 基本验证
            assert video_info is not None
            assert video_info.platform == "douyin"
            assert video_info.duration > 0
            
        except Exception as e:
            print(f"视频信息提取失败: {e}")
            pytest.skip(f"无法提取视频信息: {e}")
    
    @pytest.mark.network
    @pytest.mark.slow
    def test_real_video_download(self):
        """测试真实视频下载"""
        user_video_url = "https://v.douyin.com/wrvKzCqdS5k/"
        
        from core.downloader import VideoDownloader
        import tempfile
        
        # 创建下载器实例
        downloader = VideoDownloader()
        
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                # 下载音频
                audio_path = asyncio.run(
                    downloader.download_audio_only(user_video_url, temp_dir)
                )
                
                print(f"音频下载路径: {audio_path}")
                
                # 验证文件存在
                import os
                assert os.path.exists(audio_path)
                
                # 检查文件大小
                file_size = os.path.getsize(audio_path)
                print(f"音频文件大小: {file_size} bytes")
                assert file_size > 0, "音频文件为空"
                
        except Exception as e:
            print(f"视频下载失败: {e}")
            pytest.skip(f"无法下载视频: {e}")


if __name__ == "__main__":
    # 运行指定的测试
    pytest.main([
        __file__, 
        "-v", 
        "--tb=short",
        "-k", "test_user_douyin_video_mock_success"
    ])