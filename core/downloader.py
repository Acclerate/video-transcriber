"""
音频提取模块
从本地视频文件中提取音频并进行优化
"""

import os
import asyncio
from pathlib import Path
from typing import Optional, Callable
from datetime import datetime

from pydub import AudioSegment
from loguru import logger

from models.schemas import VideoFileInfo, VideoFormat


class AudioExtractor:
    """音频提取器"""

    def __init__(self, temp_dir: str = "./temp", cleanup_after: int = 3600):
        """
        初始化提取器

        Args:
            temp_dir: 临时文件目录
            cleanup_after: 清理文件的时间间隔(秒)
        """
        self.temp_dir = Path(temp_dir)
        self.cleanup_after = cleanup_after

        # 确保临时目录存在
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        # 支持的视频格式
        self.supported_formats = {
            VideoFormat.MP4: ['.mp4', '.m4v'],
            VideoFormat.AVI: ['.avi'],
            VideoFormat.MKV: ['.mkv'],
            VideoFormat.MOV: ['.mov'],
            VideoFormat.WMV: ['.wmv'],
            VideoFormat.FLV: ['.flv'],
            VideoFormat.WEBM: ['.webm'],
            VideoFormat.MPEG: ['.mpeg', '.mpg', '.mp2', '.mp3'],
        }

    def get_video_info(self, file_path: str) -> VideoFileInfo:
        """
        获取视频文件信息

        Args:
            file_path: 视频文件路径

        Returns:
            VideoFileInfo: 视频文件信息
        """
        try:
            path = Path(file_path)

            if not path.exists():
                raise FileNotFoundError(f"文件不存在: {file_path}")

            if not path.is_file():
                raise ValueError(f"路径不是文件: {file_path}")

            # 获取文件信息
            file_name = path.name
            file_size = path.stat().st_size
            file_ext = path.suffix.lower()

            # 检测视频格式
            format_type = self._detect_format(file_ext)

            # 获取视频时长
            duration = self._get_video_duration(file_path)

            return VideoFileInfo(
                file_path=str(path.absolute()),
                file_name=file_name,
                file_size=file_size,
                duration=duration,
                format=format_type
            )

        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            raise Exception(f"获取视频信息失败: {str(e)}")

    def _detect_format(self, file_ext: str) -> VideoFormat:
        """检测视频格式"""
        for format_type, extensions in self.supported_formats.items():
            if file_ext in extensions:
                return format_type
        # 默认返回扩展名作为格式
        return VideoFormat(file_ext.lstrip('.'))

    def _get_video_duration(self, file_path: str) -> Optional[float]:
        """获取视频时长"""
        try:
            # 使用pydub加载音频来获取时长
            audio = AudioSegment.from_file(file_path)
            return len(audio) / 1000.0  # 转换为秒
        except Exception as e:
            logger.warning(f"无法获取视频时长: {e}")
            return None

    async def extract_audio(
        self,
        video_path: str,
        output_format: str = "wav",
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> str:
        """
        从视频文件中提取音频

        Args:
            video_path: 视频文件路径
            output_format: 输出音频格式 (wav, mp3, m4a)
            progress_callback: 进度回调函数

        Returns:
            str: 提取的音频文件路径
        """
        try:
            logger.info(f"开始提取音频: {video_path}")

            if not os.path.exists(video_path):
                raise Exception(f"视频文件不存在: {video_path}")

            # 模拟进度
            if progress_callback:
                progress_callback(10)

            # 生成音频文件路径
            video_name = Path(video_path).stem
            audio_path = self.temp_dir / f"{video_name}_extracted.{output_format}"

            # 使用pydub提取音频
            if progress_callback:
                progress_callback(30)

            audio = AudioSegment.from_file(video_path)

            if progress_callback:
                progress_callback(60)

            # 音频导出设置
            if output_format.lower() == "wav":
                # 转换为16kHz单声道WAV (语音识别推荐格式)
                audio = audio.set_frame_rate(16000).set_channels(1)
                audio.export(str(audio_path), format="wav")
            elif output_format.lower() == "mp3":
                audio = audio.set_frame_rate(44100)
                audio.export(str(audio_path), format="mp3", bitrate="192k")
            else:
                audio.export(str(audio_path), format=output_format)

            if progress_callback:
                progress_callback(100)

            logger.info(f"音频提取完成: {audio_path}")
            return str(audio_path)

        except Exception as e:
            logger.error(f"音频提取失败: {e}")
            raise Exception(f"音频提取失败: {str(e)}")

    async def optimize_audio_for_transcription(
        self,
        audio_path: str,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> str:
        """
        优化音频文件以提高转录准确率

        Args:
            audio_path: 原始音频文件路径
            progress_callback: 进度回调函数

        Returns:
            str: 优化后的音频文件路径
        """
        try:
            logger.info(f"开始优化音频: {audio_path}")

            if not os.path.exists(audio_path):
                raise Exception(f"音频文件不存在: {audio_path}")

            if progress_callback:
                progress_callback(20)

            # 加载音频
            audio = AudioSegment.from_file(audio_path)

            if progress_callback:
                progress_callback(40)

            # 音频优化处理
            # 1. 转换为16kHz单声道 (语音识别最佳格式)
            audio = audio.set_frame_rate(16000).set_channels(1)

            # 2. 音量标准化
            try:
                target_dBFS = -20.0
                change_in_dBFS = target_dBFS - audio.dBFS
                audio = audio.apply_gain(change_in_dBFS)
            except Exception as e:
                logger.warning(f"音量标准化失败: {e}")

            if progress_callback:
                progress_callback(60)

            # 3. 去除静音片段
            audio = self._remove_silence(audio)

            if progress_callback:
                progress_callback(80)

            # 生成优化后的文件路径
            audio_name = Path(audio_path).stem
            optimized_path = self.temp_dir / f"{audio_name}_optimized.wav"

            # 导出优化后的音频
            audio.export(str(optimized_path), format="wav")

            if progress_callback:
                progress_callback(100)

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

    async def extract_and_optimize(
        self,
        video_path: str,
        optimize: bool = True,
        progress_callback: Optional[Callable[[float], None]] = None
    ) -> str:
        """
        提取音频并优化

        Args:
            video_path: 视频文件路径
            optimize: 是否优化音频
            progress_callback: 进度回调

        Returns:
            str: 音频文件路径
        """
        try:
            # 提取音频
            audio_path = await self.extract_audio(
                video_path=video_path,
                output_format="wav",
                progress_callback=lambda p: progress_callback(p * 0.5) if progress_callback else None
            )

            # 优化音频
            if optimize:
                optimized_path = await self.optimize_audio_for_transcription(
                    audio_path=audio_path,
                    progress_callback=lambda p: progress_callback(50 + p * 0.5) if progress_callback else None
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
            logger.error(f"音频提取和优化失败: {e}")
            raise

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

            import time
            current_time = time.time()
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


# 全局提取器实例
audio_extractor = AudioExtractor()


async def extract_audio_from_video(
    video_path: str,
    optimize: bool = True,
    progress_callback: Optional[Callable[[float], None]] = None
) -> str:
    """
    从视频文件提取音频的便捷函数

    Args:
        video_path: 视频文件路径
        optimize: 是否优化音频
        progress_callback: 进度回调

    Returns:
        str: 音频文件路径
    """
    return await audio_extractor.extract_and_optimize(
        video_path=video_path,
        optimize=optimize,
        progress_callback=progress_callback
    )


if __name__ == "__main__":
    # 测试代码
    import asyncio

    async def test():
        extractor = AudioExtractor()

        try:
            print("测试提取器初始化...")
            print(f"临时目录: {extractor.temp_dir}")
            print(f"目录大小: {extractor.get_temp_dir_size()} 字节")

            # 测试清理
            cleaned = extractor.cleanup_files(0)  # 清理所有文件
            print(f"清理文件数: {cleaned}")

        except Exception as e:
            print(f"测试失败: {e}")

    # asyncio.run(test())
