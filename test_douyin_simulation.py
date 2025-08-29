"""
模拟抖音视频转录测试
由于抖音的反爬虫机制，我们使用模拟数据演示转录功能
"""

import asyncio
import sys
import tempfile
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from core.transcriber import SpeechTranscriber
from models.schemas import VideoInfo, Platform
import numpy as np
import soundfile as sf


def create_sample_audio(duration_seconds: int = 10) -> str:
    """
    创建一个示例音频文件用于测试
    
    Args:
        duration_seconds: 音频时长（秒）
        
    Returns:
        str: 音频文件路径
    """
    # 生成简单的正弦波音频（440Hz，A音）
    sample_rate = 16000
    t = np.linspace(0, duration_seconds, int(sample_rate * duration_seconds))
    
    # 创建多频率混合音频，模拟人声
    frequencies = [440, 880, 220]  # A4, A5, A3
    audio_data = np.zeros_like(t)
    
    for freq in frequencies:
        audio_data += 0.3 * np.sin(2 * np.pi * freq * t)
    
    # 添加一些噪声，使其更像真实音频
    noise = np.random.normal(0, 0.05, len(audio_data))
    audio_data += noise
    
    # 标准化音频
    audio_data = audio_data / np.max(np.abs(audio_data)) * 0.8
    
    # 保存到临时文件
    temp_dir = Path("./temp")
    temp_dir.mkdir(exist_ok=True)
    
    audio_path = temp_dir / "sample_douyin_audio.wav"
    sf.write(str(audio_path), audio_data, sample_rate)
    
    return str(audio_path)


async def test_transcription_pipeline():
    """测试转录流水线"""
    
    print("🎯 模拟抖音视频转录测试")
    print("=" * 60)
    
    # 模拟用户的视频信息
    video_info = VideoInfo(
        video_id="7539111779729689902",
        title="INTJ要明白，精力才是稀有资源 INTJ生产力不够稳定？总是容易失去动力？到底是什么限制了我们？",
        platform=Platform.DOUYIN,
        duration=272.0,
        url="https://v.douyin.com/wrvKzCqdS5k/",
        thumbnail="https://example.com/thumb.jpg",
        uploader="抖音用户",
        upload_date=None,
        view_count=1000,
        description="关于INTJ人格类型和生产力的讨论视频"
    )
    
    print("📹 视频信息:")
    print(f"   标题: {video_info.title}")
    print(f"   平台: {video_info.platform}")
    print(f"   时长: {video_info.duration}秒")
    print(f"   视频ID: {video_info.video_id}")
    
    # 步骤1: 创建示例音频（模拟下载）
    print("\n1️⃣ 创建示例音频（模拟下载）...")
    try:
        audio_path = create_sample_audio(10)  # 创建10秒的示例音频
        print(f"   ✅ 音频创建成功: {audio_path}")
        
        # 检查文件
        if os.path.exists(audio_path):
            file_size = os.path.getsize(audio_path)
            print(f"   📁 文件大小: {file_size / 1024:.2f} KB")
    except Exception as e:
        print(f"   ❌ 音频创建失败: {e}")
        return
    
    # 步骤2: 语音转录
    print("\n2️⃣ 语音转录...")
    try:
        transcriber = SpeechTranscriber()
        await transcriber.load_model()
        print("   ✅ Whisper模型加载成功")
        
        result = await transcriber.transcribe_audio(audio_path)
        print("   ✅ 语音转录完成")
        print(f"   📝 转录文本: {result.text}")
        print(f"   🌍 识别语言: {result.language}")
        print(f"   💯 置信度: {result.confidence:.2%}")
        print(f"   ⏱️  处理时间: {result.processing_time}秒")
        print(f"   🔧 使用模型: {result.whisper_model}")
        
        if result.segments:
            print(f"   📍 时间戳片段: {len(result.segments)}段")
            for i, segment in enumerate(result.segments[:3]):
                print(f"      {i+1}. [{segment.start_time:.1f}s - {segment.end_time:.1f}s] {segment.text}")
        
    except Exception as e:
        print(f"   ❌ 语音转录失败: {e}")
        return
    
    # 步骤3: 清理文件
    print("\n3️⃣ 清理临时文件...")
    try:
        if os.path.exists(audio_path):
            os.remove(audio_path)
            print("   ✅ 临时文件清理完成")
    except Exception as e:
        print(f"   ⚠️ 清理失败: {e}")
    
    print("\n" + "=" * 60)
    print("🎉 模拟测试完成！转录功能正常运行")
    print("\n💡 关于真实抖音视频:")
    print("   由于抖音的反爬虫机制，直接下载需要有效的cookies")
    print("   建议解决方案:")
    print("   1. 配置有效的抖音cookies")
    print("   2. 使用浏览器插件或工具先下载视频文件")
    print("   3. 直接上传本地视频文件进行转录")


async def test_with_cookies():
    """演示如何配置cookies进行真实测试"""
    
    print("\n🍪 Cookie配置说明:")
    print("1. 在浏览器中登录抖音")
    print("2. 访问一个抖音视频页面")
    print("3. 打开开发者工具 (F12)")
    print("4. 在Network选项卡中找到请求头")
    print("5. 复制Cookie信息")
    print("6. 在项目中创建cookies.txt文件")
    print("\nCookie文件格式示例:")
    print("# Netscape HTTP Cookie File")
    print("douyin.com\tTRUE\t/\tFALSE\t0\tsessionid\tyour_session_id")
    print("douyin.com\tTRUE\t/\tFALSE\t0\tother_cookie\tother_value")


if __name__ == "__main__":
    print("🚀 启动抖音视频转录测试")
    print("由于需要cookies，我们将运行模拟测试")
    
    # 运行模拟测试
    asyncio.run(test_transcription_pipeline())
    
    # 显示cookie配置说明
    asyncio.run(test_with_cookies())