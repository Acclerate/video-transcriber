"""
测试视频解析器模块
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch
from urllib.parse import urlparse

from core.parser import VideoLinkParser, video_parser
from models.schemas import Platform, VideoInfo
from tests.conftest import requires_network


class TestVideoLinkParser:
    """视频链接解析器测试"""
    
    def test_detect_platform_douyin(self):
        """测试抖音平台检测"""
        parser = VideoLinkParser()
        
        test_urls = [
            "https://v.douyin.com/ieFvvPLX/",
            "https://www.douyin.com/video/7123456789",
            "https://www.iesdouyin.com/share/video/123456"
        ]
        
        for url in test_urls:
            platform = parser.detect_platform(url)
            assert platform == Platform.DOUYIN
    
    def test_detect_platform_bilibili(self):
        """测试B站平台检测"""
        parser = VideoLinkParser()
        
        test_urls = [
            "https://www.bilibili.com/video/BV1234567890",
            "https://b23.tv/abcdef",
            "https://bilibili.com/video/av123456"
        ]
        
        for url in test_urls:
            platform = parser.detect_platform(url)
            assert platform == Platform.BILIBILI
    
    def test_detect_platform_unknown(self):
        """测试未知平台检测"""
        parser = VideoLinkParser()
        
        test_urls = [
            "https://www.youtube.com/watch?v=test",
            "https://www.tiktok.com/@user/video/123",
            "https://example.com/video/123"
        ]
        
        for url in test_urls:
            platform = parser.detect_platform(url)
            assert platform == Platform.UNKNOWN
    
    def test_extract_douyin_id(self):
        """测试抖音视频ID提取"""
        parser = VideoLinkParser()
        
        test_cases = [
            ("https://www.douyin.com/video/7123456789", "7123456789"),
            ("https://v.douyin.com/ieFvvPLX/", "ieFvvPLX"),
        ]
        
        for url, expected_id in test_cases:
            video_id = parser.extract_video_id(url, Platform.DOUYIN)
            assert video_id == expected_id
    
    def test_extract_bilibili_id(self):
        """测试B站视频ID提取"""
        parser = VideoLinkParser()
        
        test_cases = [
            ("https://www.bilibili.com/video/BV1234567890", "BV1234567890"),
            ("https://www.bilibili.com/video/av123456", "av123456"),
        ]
        
        for url, expected_id in test_cases:
            video_id = parser.extract_video_id(url, Platform.BILIBILI)
            assert video_id == expected_id
    
    def test_validate_url_valid(self):
        """测试有效URL验证"""
        parser = VideoLinkParser()
        
        valid_urls = [
            "https://v.douyin.com/ieFvvPLX/",
            "https://www.bilibili.com/video/BV1234567890",
            "v.douyin.com/test123",  # 无协议但有效
        ]
        
        for url in valid_urls:
            assert parser.validate_url(url) is True
    
    def test_validate_url_invalid(self):
        """测试无效URL验证"""
        parser = VideoLinkParser()
        
        invalid_urls = [
            "",
            None,
            "not-a-url",
            "https://unsupported.com/video/123",
            "ftp://example.com/video",
        ]
        
        for url in invalid_urls:
            assert parser.validate_url(url) is False
    
    @patch('core.parser.yt_dlp.YoutubeDL')
    async def test_get_video_info_success(self, mock_ytdl, mock_ytdl_info):
        """测试成功获取视频信息"""
        parser = VideoLinkParser()
        
        # 模拟yt-dlp返回
        mock_instance = Mock()
        mock_instance.extract_info.return_value = mock_ytdl_info
        mock_ytdl.return_value.__enter__.return_value = mock_instance
        
        url = "https://v.douyin.com/test123"
        video_info = await parser.get_video_info(url)
        
        assert isinstance(video_info, VideoInfo)
        assert video_info.video_id == "test_video_123"
        assert video_info.title == "测试视频标题"
        assert video_info.platform == Platform.DOUYIN
        assert video_info.duration == 30.5
    
    @patch('core.parser.yt_dlp.YoutubeDL')
    async def test_get_video_info_failure(self, mock_ytdl):
        """测试获取视频信息失败"""
        parser = VideoLinkParser()
        
        # 模拟yt-dlp抛出异常
        mock_instance = Mock()
        mock_instance.extract_info.side_effect = Exception("视频不存在")
        mock_ytdl.return_value.__enter__.return_value = mock_instance
        
        url = "https://v.douyin.com/invalid"
        
        with pytest.raises(Exception) as exc_info:
            await parser.get_video_info(url)
        
        assert "视频解析失败" in str(exc_info.value)
    
    def test_get_supported_platforms(self):
        """测试获取支持的平台列表"""
        parser = VideoLinkParser()
        platforms = parser.get_supported_platforms()
        
        assert isinstance(platforms, dict)
        assert Platform.DOUYIN.value in platforms
        assert Platform.BILIBILI.value in platforms
        
        douyin_info = platforms[Platform.DOUYIN.value]
        assert douyin_info["name"] == Platform.DOUYIN.value
        assert douyin_info["display_name"] == "抖音"
        assert douyin_info["supported"] is True
        assert len(douyin_info["domains"]) > 0
    
    async def test_parse_video_url_convenience_function(self, mock_ytdl_info):
        """测试便捷函数parse_video_url"""
        from core.parser import parse_video_url
        
        with patch('core.parser.video_parser.get_video_info') as mock_get_info:
            mock_get_info.return_value = VideoInfo(
                video_id="test_123",
                title="测试视频",
                platform=Platform.DOUYIN,
                duration=30.0,
                url="https://v.douyin.com/test123",
                thumbnail=None,
                uploader=None,
                upload_date=None,
                view_count=None,
                description=None
            )
            
            result = await parse_video_url("https://v.douyin.com/test123")
            
            assert isinstance(result, VideoInfo)
            assert result.video_id == "test_123"
            mock_get_info.assert_called_once()
    
    def test_validate_video_url_convenience_function(self):
        """测试便捷函数validate_video_url"""
        from core.parser import validate_video_url
        
        assert validate_video_url("https://v.douyin.com/test123") is True
        assert validate_video_url("invalid-url") is False
    
    def test_detect_video_platform_convenience_function(self):
        """测试便捷函数detect_video_platform"""
        from core.parser import detect_video_platform
        
        assert detect_video_platform("https://v.douyin.com/test123") == Platform.DOUYIN
        assert detect_video_platform("https://www.bilibili.com/video/BV123") == Platform.BILIBILI
        assert detect_video_platform("https://unsupported.com/video") == Platform.UNKNOWN


class TestVideoParserIntegration:
    """视频解析器集成测试"""
    
    def test_parser_initialization(self):
        """测试解析器初始化"""
        parser = VideoLinkParser()
        
        assert parser.platform_patterns
        assert Platform.DOUYIN in parser.platform_patterns
        assert Platform.BILIBILI in parser.platform_patterns
        assert parser.ytdl_opts
        assert "user_agent" in parser.ytdl_opts
    
    @pytest.mark.parametrize("url,expected_platform", [
        ("https://v.douyin.com/test", Platform.DOUYIN),
        ("https://www.bilibili.com/video/BV123", Platform.BILIBILI),
        ("https://unknown.com/video", Platform.UNKNOWN),
    ])
    def test_platform_detection_parametrized(self, url, expected_platform):
        """参数化测试平台检测"""
        parser = VideoLinkParser()
        result = parser.detect_platform(url)
        assert result == expected_platform
    
    def test_ytdl_options_configuration(self):
        """测试yt-dlp选项配置"""
        parser = VideoLinkParser()
        opts = parser.ytdl_opts
        
        # 验证关键配置项
        assert opts["quiet"] is True
        assert opts["no_warnings"] is True
        assert opts["skip_download"] is True
        assert "user_agent" in opts
    
    @requires_network
    async def test_real_video_info_extraction(self):
        """测试真实视频信息提取（需要网络）"""
        parser = VideoLinkParser()
        
        # 注意：这个测试需要真实的网络连接和有效的视频链接
        # 在CI/CD环境中可能需要跳过
        test_url = "https://v.douyin.com/ieFvvPLX/"  # 替换为实际有效的测试链接
        
        try:
            video_info = await parser.get_video_info(test_url)
            assert isinstance(video_info, VideoInfo)
            assert video_info.video_id
            assert video_info.title
        except Exception as e:
            pytest.skip(f"网络测试跳过: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])