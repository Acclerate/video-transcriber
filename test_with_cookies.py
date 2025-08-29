"""
使用真实Cookies测试抖音视频转录
"""

import asyncio
import sys
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.parser import VideoLinkParser
from core.downloader import VideoDownloader  
from core.transcriber import SpeechTranscriber
from models.schemas import Platform
from utils.helpers import validate_url
from loguru import logger


async def test_real_douyin_video():
    """使用真实cookies测试抖音视频转录"""
    
    # 用户的抖音视频链接
    user_video_url = "https://v.douyin.com/wrvKzCqdS5k/"
    
    print(f"🎯 使用真实Cookies测试抖音视频转录")
    print(f"📹 视频链接: {user_video_url}")
    print("=" * 60)
    
    # 检查cookies文件
    cookies_path = Path("./cookies.txt")
    if not cookies_path.exists():
        print("❌ 未找到cookies.txt文件")
        print("请确保已创建cookies.txt文件并包含有效的抖音cookies")
        return
    else:
        print("✅ 找到cookies.txt文件")
    
    # 步骤1: URL验证
    print("\n1️⃣ 验证URL格式...")
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
    
    # 步骤4: 音频下载（使用cookies）
    print("\n4️⃣ 下载音频（使用cookies）...")
    downloader = VideoDownloader()
    
    try:
        # 这里会自动使用cookies.txt文件
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
        print("   💡 请检查cookies是否有效或是否已过期")
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
            for i, segment in enumerate(result.segments[:5]):  # 显示前5段
                print(f"      {i+1}. [{segment.start_time:.1f}s - {segment.end_time:.1f}s] {segment.text}")
            
            if len(result.segments) > 5:
                print(f"      ... 还有 {len(result.segments) - 5} 段")
        
    except Exception as e:
        print(f"   ❌ 语音转录失败: {e}")
        return
    
    # 步骤7: 保存结果
    print("\n7️⃣ 保存转录结果...")
    try:
        result_file = Path("./temp") / f"{video_info.video_id}_transcription.txt"
        result_file.parent.mkdir(exist_ok=True)
        
        with open(result_file, 'w', encoding='utf-8') as f:
            f.write(f"视频标题: {video_info.title}\n")
            f.write(f"视频链接: {user_video_url}\n")
            f.write(f"时长: {video_info.duration}秒\n")
            f.write(f"转录语言: {result.language}\n")
            f.write(f"置信度: {result.confidence:.2%}\n")
            f.write(f"处理时间: {result.processing_time}秒\n")
            f.write(f"使用模型: {result.whisper_model}\n")
            f.write("\n" + "="*50 + "\n")
            f.write("转录文本:\n")
            f.write(result.text)
            f.write("\n\n" + "="*50 + "\n")
            f.write("时间戳片段:\n")
            
            for i, segment in enumerate(result.segments):
                f.write(f"{i+1}. [{segment.start_time:.1f}s - {segment.end_time:.1f}s] {segment.text}\n")
        
        print(f"   ✅ 转录结果已保存: {result_file}")
        
    except Exception as e:
        print(f"   ⚠️ 保存结果失败: {e}")
    
    # 步骤8: 清理临时文件
    print("\n8️⃣ 清理临时文件...")
    try:
        cleaned_count = downloader.cleanup_files(0)  # 立即清理
        print(f"   ✅ 清理了 {cleaned_count} 个文件")
    except Exception as e:
        print(f"   ⚠️ 清理失败: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 抖音视频转录完成！")
    print("✨ 您的视频已成功转录为文字")


if __name__ == "__main__":
    print("🚀 启动抖音视频转录测试")
    print("🍪 使用cookies.txt中的认证信息")
    
    asyncio.run(test_real_douyin_video())