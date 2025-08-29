"""
视频下载和音频提取模块
支持从各种视频平台下载视频并提取音频
"""

import os
import asyncio
import tempfile
import shutil
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from urllib.parse import urlparse

import yt_dlp
from pydub import AudioSegment
from loguru import logger

from models.schemas import VideoInfo, Platform


class VideoDownloader:
    """视频下载器"""
    
    def __init__(self, temp_dir: str = "./temp", cleanup_after: int = 3600):
        """
        初始化下载器
        
        Args:
            temp_dir: 临时文件目录
            cleanup_after: 清理文件的时间间隔(秒)
        """
        self.temp_dir = Path(temp_dir)
        self.cleanup_after = cleanup_after
        
        # 确保临时目录存在
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        
        # yt-dlp基础配置
        self.base_ytdl_opts = {
            'format': 'best[height<=720]',  # 优先选择720p以下的视频
            'outtmpl': str(self.temp_dir / '%(id)s.%(ext)s'),
            'writeinfojson': False,
            'writesubtitles': False,
            'writeautomaticsub': False,
            'ignoreerrors': True,
            'no_warnings': False,
            'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'extractor_retries': 3,
            'retries': 3,
        }
    
    async def download_video(
        self, 
        video_info: VideoInfo, 
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> str:
        """
        下载视频文件
        
        Args:
            video_info: 视频信息
            progress_callback: 进度回调函数
            
        Returns:
            str: 下载的视频文件路径
        """
        try:
            logger.info(f"开始下载视频: {video_info.title}")
            
            # 设置进度回调
            ytdl_opts = self.base_ytdl_opts.copy()
            if progress_callback:
                ytdl_opts['progress_hooks'] = [self._progress_hook(progress_callback)]
            
            # 根据平台调整配置
            ytdl_opts = self._adjust_opts_for_platform(ytdl_opts, video_info.platform)
            
            # 执行下载
            video_path = await self._download_with_ytdlp(str(video_info.url), ytdl_opts)
            
            if not video_path or not os.path.exists(video_path):
                raise Exception("视频下载失败，文件不存在")
            
            logger.info(f"视频下载完成: {video_path}")
            return video_path
            
        except Exception as e:
            logger.error(f"视频下载失败: {e}")
            raise Exception(f"视频下载失败: {str(e)}")
    
    async def download_audio_only(
        self, 
        video_info: VideoInfo,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> str:
        """
        直接下载音频文件
        
        Args:
            video_info: 视频信息
            progress_callback: 进度回调函数
            
        Returns:
            str: 下载的音频文件路径
        """
        try:
            logger.info(f"开始下载音频: {video_info.title}")
            
            # 配置仅下载音频
            ytdl_opts = self.base_ytdl_opts.copy()
            ytdl_opts.update({
                'format': 'bestaudio/best',
                'outtmpl': str(self.temp_dir / '%(id)s_audio.%(ext)s'),
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }]
            })
            
            if progress_callback:
                ytdl_opts['progress_hooks'] = [self._progress_hook(progress_callback)]
            
            # 根据平台调整配置
            ytdl_opts = self._adjust_opts_for_platform(ytdl_opts, video_info.platform)
            
            # 执行下载
            audio_path = await self._download_with_ytdlp(str(video_info.url), ytdl_opts)
            
            # 检查生成的音频文件
            if not audio_path:
                # 查找可能的音频文件
                possible_files = list(self.temp_dir.glob(f"{video_info.video_id}*"))
                for file_path in possible_files:
                    if file_path.suffix.lower() in ['.mp3', '.m4a', '.wav', '.aac']:
                        audio_path = str(file_path)
                        break
            
            if not audio_path or not os.path.exists(audio_path):
                raise Exception("音频下载失败，文件不存在")
            
            logger.info(f"音频下载完成: {audio_path}")
            return audio_path
            
        except Exception as e:
            logger.error(f"音频下载失败: {e}")
            raise Exception(f"音频下载失败: {str(e)}")
    
    async def extract_audio(self, video_path: str, output_format: str = "wav") -> str:
        """
        从视频文件中提取音频
        
        Args:
            video_path: 视频文件路径
            output_format: 输出音频格式 (wav, mp3, m4a)
            
        Returns:
            str: 提取的音频文件路径
        """
        try:
            logger.info(f"开始提取音频: {video_path}")
            
            if not os.path.exists(video_path):
                raise Exception(f"视频文件不存在: {video_path}")
            
            # 生成音频文件路径
            video_name = Path(video_path).stem
            audio_path = self.temp_dir / f"{video_name}_extracted.{output_format}"
            
            # 使用pydub提取音频
            audio = AudioSegment.from_file(video_path)
            
            # 音频优化设置
            if output_format.lower() == "wav":
                # 转换为16kHz单声道WAV (Whisper推荐格式)
                audio = audio.set_frame_rate(16000).set_channels(1)
                audio.export(str(audio_path), format="wav")
            elif output_format.lower() == "mp3":
                audio = audio.set_frame_rate(44100)
                audio.export(str(audio_path), format="mp3", bitrate="192k")
            else:
                audio.export(str(audio_path), format=output_format)
            
            logger.info(f"音频提取完成: {audio_path}")
            return str(audio_path)
            
        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            raise Exception(f"音频提取失败: {str(e)}")
    
    async def optimize_audio_for_transcription(self, audio_path: str) -> str:
        """
        优化音频文件以提高转录准确率
        
        Args:
            audio_path: 原始音频文件路径
            
        Returns:
            str: 优化后的音频文件路径
        """
        try:
            logger.info(f"开始优化音频: {audio_path}")
            
            if not os.path.exists(audio_path):
                raise Exception(f"音频文件不存在: {audio_path}")
            
            # 加载音频
            audio = AudioSegment.from_file(audio_path)
            
            # 音频优化处理
            # 1. 转换为16kHz单声道 (Whisper最佳格式)
            audio = audio.set_frame_rate(16000).set_channels(1)
            
            # 2. 音量标准化
            target_dBFS = -20.0
            change_in_dBFS = target_dBFS - audio.dBFS
            audio = audio.apply_gain(change_in_dBFS)
            
            # 3. 去除静音片段
            audio = self._remove_silence(audio)
            
            # 生成优化后的文件路径
            audio_name = Path(audio_path).stem
            optimized_path = self.temp_dir / f"{audio_name}_optimized.wav"
            
            # 导出优化后的音频
            audio.export(str(optimized_path), format="wav")
            
            logger.info(f"音频优化完成: {optimized_path}")
            return str(optimized_path)
            
        except Exception as e:
            logger.error(f"音频优化失败: {e}")
            raise Exception(f"音频优化失败: {str(e)}")
    
    def _remove_silence(self, audio: AudioSegment, silence_thresh: int = -40) -> AudioSegment:
        """去除音频中的静音片段"""
        try:
            from pydub.silence import split_on_silence
            
            # 分割静音片段
            chunks = split_on_silence(
                audio,
                min_silence_len=1000,  # 最小静音长度1秒
                silence_thresh=silence_thresh,  # 静音阈值
                keep_silence=500  # 保留500ms静音
            )
            
            if chunks:
                # 重新组合非静音片段
                result = AudioSegment.empty()
                for chunk in chunks:
                    result += chunk
                return result
            else:
                return audio
                
        except ImportError:
            # 如果没有pydub.silence，返回原音频
            logger.warning("pydub.silence不可用，跳过静音移除")
            return audio
        except Exception as e:
            logger.warning(f"静音移除失败: {e}")
            return audio
    
    async def _download_with_ytdlp(self, url: str, ytdl_opts: Dict[str, Any]) -> Optional[str]:
        """使用yt-dlp下载"""
        def _download():
            downloaded_files = []
            
            def progress_hook(d):
                if d['status'] == 'finished':
                    downloaded_files.append(d['filename'])
            
            ytdl_opts_copy = ytdl_opts.copy()
            if 'progress_hooks' not in ytdl_opts_copy:
                ytdl_opts_copy['progress_hooks'] = []
            ytdl_opts_copy['progress_hooks'].append(progress_hook)
            
            try:
                with yt_dlp.YoutubeDL(ytdl_opts_copy) as ydl:
                    ydl.download([url])
                
                # 返回下载的文件路径
                if downloaded_files:
                    return downloaded_files[0]
                else:
                    # 尝试根据模板查找文件
                    outtmpl = ytdl_opts.get('outtmpl', '')
                    if outtmpl:
                        # 简单的文件查找逻辑
                        temp_files = list(self.temp_dir.glob("*"))
                        if temp_files:
                            return str(max(temp_files, key=os.path.getctime))
                    return None
                    
            except Exception as e:
                logger.error(f"yt-dlp下载失败: {e}")
                raise
        
        # 在线程池中执行下载
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, _download)
    
    def _progress_hook(self, callback: Callable[[float], None]):
        """创建进度回调钩子"""
        def hook(d):
            if d['status'] == 'downloading':
                try:
                    if 'total_bytes' in d and d['total_bytes']:
                        progress = (d['downloaded_bytes'] / d['total_bytes']) * 100
                    elif '_percent_str' in d:
                        progress_str = d['_percent_str'].replace('%', '').strip()
                        progress = float(progress_str)
                    else:
                        progress = 0
                    
                    callback(min(100, max(0, progress)))
                except (ValueError, KeyError, TypeError):
                    pass
        
        return hook
    
    def _adjust_opts_for_platform(self, opts: Dict[str, Any], platform: Platform) -> Dict[str, Any]:
        """根据平台调整下载选项"""
        if platform == Platform.DOUYIN:
            # 抖音特殊配置
            opts.update({
                'format': 'best[height<=720]',
                'user_agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15',
                'headers': {
                    'Referer': 'https://www.douyin.com/',
                }
            })
        elif platform == Platform.BILIBILI:
            # B站特殊配置
            opts.update({
                'format': 'best[height<=720]',
                'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'headers': {
                    'Referer': 'https://www.bilibili.com/',
                }
            })
        
        return opts
    
    def cleanup_files(self, older_than_seconds: Optional[int] = None) -> int:
        """
        清理临时文件
        
        Args:
            older_than_seconds: 清理早于指定秒数的文件，None则使用默认值
            
        Returns:
            int: 清理的文件数量
        """
        try:
            if older_than_seconds is None:
                older_than_seconds = self.cleanup_after
            
            current_time = asyncio.get_event_loop().time()
            cleaned_count = 0
            
            for file_path in self.temp_dir.iterdir():
                if file_path.is_file():
                    file_age = current_time - file_path.stat().st_mtime
                    if file_age > older_than_seconds:
                        try:
                            file_path.unlink()
                            cleaned_count += 1
                            logger.debug(f"清理文件: {file_path}")
                        except Exception as e:
                            logger.warning(f"清理文件失败: {file_path}, {e}")
            
            if cleaned_count > 0:
                logger.info(f"清理了 {cleaned_count} 个临时文件")
            
            return cleaned_count
            
        except Exception as e:
            logger.error(f"文件清理失败: {e}")
            return 0
    
    def get_temp_dir_size(self) -> int:
        """获取临时目录大小(字节)"""
        try:
            total_size = 0
            for file_path in self.temp_dir.rglob('*'):
                if file_path.is_file():
                    total_size += file_path.stat().st_size
            return total_size
        except Exception:
            return 0
    
    def __del__(self):
        """析构函数，清理资源"""
        try:
            # 可以在这里添加清理逻辑
            pass
        except Exception:
            pass


# 全局下载器实例
video_downloader = VideoDownloader()


async def download_video_and_extract_audio(
    video_info: VideoInfo,
    audio_format: str = "wav",
    optimize: bool = True,
    progress_callback: Optional[Callable[[float], None]] = None
) -> str:
    """
    下载视频并提取音频的便捷函数
    
    Args:
        video_info: 视频信息
        audio_format: 音频格式
        optimize: 是否优化音频
        progress_callback: 进度回调
        
    Returns:
        str: 音频文件路径
    """
    try:
        # 尝试直接下载音频
        try:
            audio_path = await video_downloader.download_audio_only(
                video_info, progress_callback
            )
        except Exception:
            # 如果直接下载音频失败，则下载视频后提取音频
            logger.info("直接下载音频失败，尝试下载视频后提取")
            video_path = await video_downloader.download_video(
                video_info, progress_callback
            )
            audio_path = await video_downloader.extract_audio(
                video_path, audio_format
            )
            
            # 清理视频文件
            try:
                os.remove(video_path)
            except Exception:
                pass
        
        # 优化音频
        if optimize:
            optimized_path = await video_downloader.optimize_audio_for_transcription(
                audio_path
            )
            
            # 清理原音频文件
            try:
                if audio_path != optimized_path:
                    os.remove(audio_path)
            except Exception:
                pass
            
            return optimized_path
        
        return audio_path
        
    except Exception as e:
        logger.error(f"视频下载和音频提取失败: {e}")
        raise


if __name__ == "__main__":
    # 测试代码
    import asyncio
    from models.schemas import VideoInfo, Platform
    
    async def test():
        downloader = VideoDownloader()
        
        # 测试视频信息
        test_video = VideoInfo(
            video_id="test123",
            title="测试视频",
            platform=Platform.BILIBILI,
            duration=30.0,
            url="https://example.com/test.mp4",
            thumbnail=None,
            uploader=None,
            upload_date=None,
            view_count=None,
            description=None
        )
        
        try:
            # 测试下载 (需要有效的视频URL)
            print("测试下载器初始化...")
            print(f"临时目录: {downloader.temp_dir}")
            print(f"目录大小: {downloader.get_temp_dir_size()} 字节")
            
            # 测试清理
            cleaned = downloader.cleanup_files(0)  # 清理所有文件
            print(f"清理文件数: {cleaned}")
            
        except Exception as e:
            print(f"测试失败: {e}")
    
    # asyncio.run(test())