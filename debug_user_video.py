"""
调试用户抖音视频的处理流程
"""

import asyncio
import sys
from pathlib import Path
import yt_dlp

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.parser import VideoLinkParser
from core.downloader import VideoDownloader  
from core.transcriber import SpeechTranscriber
from models.schemas import Platform
from utils.helpers import validate_url
from loguru import logger


async def debug_user_video():
    """调试用户视频处理流程"""
    
    # 用户的抖音视频链接
    user_video_url = "https://v.douyin.com/wrvKzCqdS5k/"
    
    print(f"🎯 开始调试用户视频: {user_video_url}")
    print("=" * 60)
    
    # 步骤1: URL验证
    print("1️⃣ 验证URL格式...")
    is_valid = validate_url(user_video_url)
    print(f"   URL验证结果: {'✅ 有效' if is_valid else '❌ 无效'}")
    
    if not is_valid:
        print("❌ URL格式无效，终止测试")
        return
    
    # 步骤2: 平台检测
    print("\n2️⃣ 检测视频平台...")
    parser = VideoLinkParser()
    platform = parser.detect_platform(user_video_url)
    print(f"   检测到平台: {platform}")
    
    if platform == Platform.UNKNOWN:
        print("❌ 不支持的平台，终止测试")
        return
    
    # 步骤3: 视频信息获取
    print("\n3️⃣ 获取视频信息...")
    try:
        video_info = await parser.get_video_info(user_video_url)
        print("   ✅ 视频信息获取成功")
        print(f"   📹 标题: {video_info.title}")
        print(f"   ⏱️  时长: {video_info.duration}秒")
        print(f"   👤 上传者: {video_info.uploader}")
        print(f"   📊 观看数: {video_info.view_count}")
        print(f"   🆔 视频ID: {video_info.video_id}")
    except Exception as e:
        print(f"   ❌ 视频信息获取失败: {e}")
        return
    
    # 步骤4: 音频下载
    print("\n4️⃣ 下载音频...")
    downloader = VideoDownloader()
    
    try:
        audio_path = await downloader.download_audio_only(video_info)
        print(f"   ✅ 音频下载成功: {audio_path}")
        
        # 检查文件
        import os
        if os.path.exists(audio_path):
            file_size = os.path.getsize(audio_path)
            print(f"   📁 文件大小: {file_size / 1024 / 1024:.2f} MB")
        else:
            print("   ❌ 音频文件不存在")
            return
            
    except Exception as e:
        print(f"   ❌ 音频下载失败: {e}")
        return
    
    # 步骤5: 音频优化
    print("\n5️⃣ 优化音频...")
    try:
        optimized_path = await downloader.optimize_audio_for_transcription(audio_path)
        print(f"   ✅ 音频优化成功: {optimized_path}")
    except Exception as e:
        print(f"   ❌ 音频优化失败: {e}")
        # 使用原始音频继续
        optimized_path = audio_path
    
    # 步骤6: 语音转录
    print("\n6️⃣ 语音转录...")
    try:
        transcriber = SpeechTranscriber()
        await transcriber.load_model()
        
        result = await transcriber.transcribe_audio(optimized_path)
        print("   ✅ 语音转录成功")
        print(f"   📝 转录文本: {result.text}")
        print(f"   🌍 识别语言: {result.language}")
        print(f"   💯 置信度: {result.confidence:.2%}")
        print(f"   ⏱️  处理时间: {result.processing_time}秒")
        print(f"   🔧 使用模型: {result.whisper_model}")
        
        # 显示时间戳
        if result.segments:
            print(f"   📍 时间戳片段: {len(result.segments)}段")
            for i, segment in enumerate(result.segments[:3]):
                print(f"      {i+1}. [{segment.start_time:.1f}s - {segment.end_time:.1f}s] {segment.text}")
        
    except Exception as e:
        print(f"   ❌ 语音转录失败: {e}")
        return
    
    # 步骤7: 清理临时文件
    print("\n7️⃣ 清理临时文件...")
    try:
        cleaned_count = downloader.cleanup_files(0)  # 立即清理
        print(f"   ✅ 清理了 {cleaned_count} 个文件")
    except Exception as e:
        print(f"   ⚠️ 清理失败: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 调试完成！所有步骤都成功执行")


async def simple_url_test():
    """简单的URL测试"""
    user_video_url = "https://v.douyin.com/wrvKzCqdS5k/"
    
    print("🔍 简单URL测试...")
    
    # 测试yt-dlp直接提取
    try:
        ytdl_opts = {
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'skip_download': True,
        }
        
        with yt_dlp.YoutubeDL(ytdl_opts) as ydl:
            info = ydl.extract_info(user_video_url, download=False)
            print("✅ yt-dlp信息提取成功")
            print(f"   标题: {info.get('title', 'N/A')}")
            print(f"   时长: {info.get('duration', 'N/A')}秒")
            print(f"   格式数量: {len(info.get('formats', []))}")
            
    except Exception as e:
        print(f"❌ yt-dlp信息提取失败: {e}")


if __name__ == "__main__":
    print("选择测试模式:")
    print("1. 完整流程调试")
    print("2. 简单URL测试")
    
    choice = input("请输入选择 (1/2): ").strip()
    
    if choice == "1":
        asyncio.run(debug_user_video())
    elif choice == "2":
        asyncio.run(simple_url_test())
    else:
        print("默认运行简单URL测试")
        asyncio.run(simple_url_test())