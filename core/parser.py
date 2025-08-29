"""
视频链接解析模块
支持抖音、B站等主流短视频平台的链接解析
"""

import re
import json
import asyncio
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Any
from datetime import datetime

import yt_dlp
from loguru import logger

from models.schemas import VideoInfo, Platform, ErrorCode, ErrorDetail


class VideoLinkParser:
    """视频链接解析器"""
    
    def __init__(self):
        self.platform_patterns = {
            Platform.DOUYIN: [
                r'douyin\.com',
                r'iesdouyin\.com',
                r'v\.douyin\.com'
            ],
            Platform.BILIBILI: [
                r'bilibili\.com',
                r'b23\.tv'
            ]
        }
        
        # yt-dlp配置
        self.ytdl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False,
            'skip_download': True,
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
    
    def detect_platform(self, url: str) -> Platform:
        """
        检测视频平台
        
        Args:
            url: 视频链接
            
        Returns:
            Platform: 检测到的平台
        """
        try:
            # 规范化URL
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # 移除www前缀
            if domain.startswith('www.'):
                domain = domain[4:]
            
            for platform, patterns in self.platform_patterns.items():
                for pattern in patterns:
                    if re.search(pattern, domain):
                        logger.debug(f"检测到平台: {platform}, URL: {url}")
                        return platform
            
            logger.warning(f"未识别的平台: {domain}, URL: {url}")
            return Platform.UNKNOWN
            
        except Exception as e:
            logger.error(f"平台检测失败: {e}, URL: {url}")
            return Platform.UNKNOWN
    
    def extract_video_id(self, url: str, platform: Platform) -> Optional[str]:
        """
        提取视频ID
        
        Args:
            url: 视频链接
            platform: 视频平台
            
        Returns:
            Optional[str]: 视频ID
        """
        try:
            if platform == Platform.DOUYIN:
                return self._extract_douyin_id(url)
            elif platform == Platform.BILIBILI:
                return self._extract_bilibili_id(url)
            else:
                logger.warning(f"不支持的平台: {platform}")
                return None
                
        except Exception as e:
            logger.error(f"视频ID提取失败: {e}, URL: {url}")
            return None
    
    def _extract_douyin_id(self, url: str) -> Optional[str]:
        """提取抖音视频ID"""
        patterns = [
            r'/video/(\d+)',
            r'video_id=(\d+)',
            r'v\.douyin\.com/([A-Za-z0-9]+)',
            r'share/video/(\d+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        
        # 如果是短链接，尝试展开
        if 'v.douyin.com' in url:
            # 这里可以添加短链接展开逻辑
            pass
        
        return None
    
    def _extract_bilibili_id(self, url: str) -> Optional[str]:
        """提取B站视频ID"""
        patterns = [
            r'BV([A-Za-z0-9]+)',
            r'av(\d+)',
            r'b23\.tv/([A-Za-z0-9]+)'
        ]
        
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1) if pattern.startswith('BV') else f"av{match.group(1)}"
        
        return None
    
    async def get_video_info(self, url: str) -> VideoInfo:
        """
        获取视频信息
        
        Args:
            url: 视频链接
            
        Returns:
            VideoInfo: 视频信息
            
        Raises:
            Exception: 解析失败时抛出异常
        """
        try:
            logger.info(f"开始解析视频信息: {url}")
            
            # 检测平台
            platform = self.detect_platform(url)
            if platform == Platform.UNKNOWN:
                raise Exception(f"不支持的平台: {url}")
            
            # 使用yt-dlp获取视频信息
            info = await self._extract_with_ytdlp(url)
            
            # 解析基本信息
            video_info = self._parse_video_info(info, platform)
            
            logger.info(f"视频信息解析成功: {video_info.title}")
            return video_info
            
        except Exception as e:
            logger.error(f"视频信息解析失败: {e}, URL: {url}")
            raise Exception(f"视频解析失败: {str(e)}")
    
    async def _extract_with_ytdlp(self, url: str) -> Dict[str, Any]:
        """使用yt-dlp提取视频信息"""
        def _extract():
            with yt_dlp.YoutubeDL(self.ytdl_opts) as ydl:
                result = ydl.extract_info(url, download=False)
                if result is None:
                    raise Exception(f"无法提取视频信息: {url}")
                return result
        
        # 在线程池中运行，避免阻塞
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _extract)
    
    def _parse_video_info(self, info: Dict[str, Any], platform: Platform) -> VideoInfo:
        """解析yt-dlp返回的视频信息"""
        try:
            # 基本信息
            video_id = info.get('id', '')
            title = info.get('title', '未知标题')
            duration = float(info.get('duration', 0))
            url = info.get('webpage_url', info.get('url', ''))
            
            # 可选信息
            thumbnail = info.get('thumbnail')
            uploader = info.get('uploader', info.get('channel', info.get('creator')))
            description = info.get('description', '')
            view_count = info.get('view_count')
            
            # 上传时间处理
            upload_date = None
            if info.get('upload_date'):
                try:
                    upload_date_str = info['upload_date']
                    upload_date = datetime.strptime(upload_date_str, '%Y%m%d')
                except (ValueError, TypeError):
                    pass
            
            return VideoInfo(
                video_id=video_id,
                title=title,
                platform=platform,
                duration=duration,
                url=url,
                thumbnail=thumbnail,
                uploader=uploader,
                upload_date=upload_date,
                view_count=view_count,
                description=description
            )
            
        except Exception as e:
            logger.error(f"视频信息解析失败: {e}")
            raise Exception(f"视频信息解析错误: {str(e)}")
    
    def validate_url(self, url: str) -> bool:
        """
        验证URL格式
        
        Args:
            url: 待验证的URL
            
        Returns:
            bool: 是否为有效URL
        """
        try:
            if not url or not isinstance(url, str):
                return False
            
            # 补全协议
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
            
            parsed = urlparse(url)
            
            # 检查基本格式
            if not parsed.netloc:
                return False
            
            # 检查是否为支持的平台
            platform = self.detect_platform(url)
            return platform != Platform.UNKNOWN
            
        except Exception:
            return False
    
    def get_supported_platforms(self) -> Dict[str, Dict[str, Any]]:
        """
        获取支持的平台列表
        
        Returns:
            Dict: 支持的平台信息
        """
        platforms = {}
        
        for platform in self.platform_patterns:
            platforms[platform.value] = {
                'name': platform.value,
                'display_name': self._get_platform_display_name(platform),
                'domains': [pattern.replace(r'\.', '.').replace('\\', '') 
                           for pattern in self.platform_patterns[platform]],
                'supported': True
            }
        
        return platforms
    
    def _get_platform_display_name(self, platform: Platform) -> str:
        """获取平台显示名称"""
        display_names = {
            Platform.DOUYIN: "抖音",
            Platform.BILIBILI: "哔哩哔哩",
            Platform.KUAISHOU: "快手",
            Platform.XIAOHONGSHU: "小红书"
        }
        return display_names.get(platform, platform.value)


# 全局解析器实例
video_parser = VideoLinkParser()


async def parse_video_url(url: str) -> VideoInfo:
    """
    解析视频URL的便捷函数
    
    Args:
        url: 视频链接
        
    Returns:
        VideoInfo: 视频信息
    """
    return await video_parser.get_video_info(url)


def validate_video_url(url: str) -> bool:
    """
    验证视频URL的便捷函数
    
    Args:
        url: 视频链接
        
    Returns:
        bool: 是否有效
    """
    return video_parser.validate_url(url)


def detect_video_platform(url: str) -> Platform:
    """
    检测视频平台的便捷函数
    
    Args:
        url: 视频链接
        
    Returns:
        Platform: 检测到的平台
    """
    return video_parser.detect_platform(url)


if __name__ == "__main__":
    # 测试代码
    import asyncio
    
    async def test():
        parser = VideoLinkParser()
        
        # 测试URLs
        test_urls = [
            "https://v.douyin.com/ieFvvPLX/",
            "https://www.bilibili.com/video/BV1234567890",
            "https://www.douyin.com/video/7123456789",
        ]
        
        for url in test_urls:
            try:
                print(f"\n测试URL: {url}")
                platform = parser.detect_platform(url)
                print(f"平台: {platform}")
                
                if parser.validate_url(url):
                    print("URL格式有效")
                    # 注意：实际测试时需要有效的视频链接
                    # video_info = await parser.get_video_info(url)
                    # print(f"视频信息: {video_info}")
                else:
                    print("URL格式无效")
                    
            except Exception as e:
                print(f"错误: {e}")
    
    # asyncio.run(test())