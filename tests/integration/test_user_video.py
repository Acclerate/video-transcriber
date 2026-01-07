"""
测试用户抖音视频转录功能的脚本
"""

import requests
import json
import time

def test_user_video_transcription():
    """测试用户提供的抖音视频转录"""
    
    # 用户的视频链接
    video_url = "https://v.douyin.com/wrvKzCqdS5k/"
    
    # API服务地址
    api_url = "http://localhost:8000/api/v1/transcribe"
    
    # 请求数据
    request_data = {
        "url": video_url,
        "options": {
            "model": "small",
            "language": "auto",
            "with_timestamps": True,
            "output_format": "json",
            "enable_gpu": True,
            "temperature": 0.0
        }
    }
    
    print(f"🎯 开始测试视频转录功能")
    print(f"📹 视频链接: {video_url}")
    print(f"🔗 API地址: {api_url}")
    print(f"⚙️  转录配置: {json.dumps(request_data['options'], ensure_ascii=False, indent=2)}")
    print("-" * 60)
    
    try:
        # 首先测试健康检查
        print("📊 检查API服务状态...")
        health_response = requests.get("http://localhost:8000/health", timeout=5)
        if health_response.status_code == 200:
            print("✅ API服务正常运行")
        else:
            print("❌ API服务异常")
            return
        
        # 发送转录请求
        print("🚀 发送转录请求...")
        start_time = time.time()
        
        response = requests.post(
            api_url,
            json=request_data,
            timeout=300  # 5分钟超时
        )
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        print(f"⏱️  请求处理时间: {processing_time:.2f}秒")
        print(f"📊 响应状态码: {response.status_code}")
        
        # 解析响应
        if response.status_code == 200:
            result = response.json()
            print("✅ 转录成功！")
            print(f"📝 响应消息: {result.get('message', 'N/A')}")
            
            # 显示转录结果
            if "data" in result and "transcription" in result["data"]:
                transcription = result["data"]["transcription"]
                print(f"\n📄 转录文本:")
                print(f"   文本内容: {transcription.get('text', 'N/A')}")
                print(f"   识别语言: {transcription.get('language', 'N/A')}")
                print(f"   置信度: {transcription.get('confidence', 'N/A'):.2%}")
                print(f"   处理时长: {transcription.get('processing_time', 'N/A')}秒")
                print(f"   使用模型: {transcription.get('whisper_model', 'N/A')}")
                
                # 显示时间戳片段
                if "segments" in transcription and transcription["segments"]:
                    print(f"\n⏰ 时间戳片段 (共{len(transcription['segments'])}段):")
                    for i, segment in enumerate(transcription["segments"][:5]):  # 只显示前5段
                        start = segment.get('start_time', 0)
                        end = segment.get('end_time', 0)
                        text = segment.get('text', '')
                        confidence = segment.get('confidence', 0)
                        print(f"   {i+1}. [{start:.1f}s - {end:.1f}s] {text} (置信度: {confidence:.2%})")
                    
                    if len(transcription["segments"]) > 5:
                        print(f"   ... 还有 {len(transcription['segments']) - 5} 段")
            
            # 显示视频信息
            if "data" in result and "video_info" in result["data"] and result["data"]["video_info"]:
                video_info = result["data"]["video_info"]
                print(f"\n📹 视频信息:")
                print(f"   标题: {video_info.get('title', 'N/A')}")
                print(f"   平台: {video_info.get('platform', 'N/A')}")
                print(f"   时长: {video_info.get('duration', 'N/A')}秒")
                print(f"   上传者: {video_info.get('uploader', 'N/A')}")
                print(f"   观看次数: {video_info.get('view_count', 'N/A')}")
        
        elif response.status_code == 400:
            error = response.json()
            print(f"❌ 请求错误: {error.get('detail', 'N/A')}")
            
        elif response.status_code == 500:
            error = response.json()
            print(f"❌ 服务器错误: {error.get('detail', 'N/A')}")
            
        else:
            print(f"❌ 未知错误: {response.status_code}")
            print(f"响应内容: {response.text}")
            
    except requests.exceptions.Timeout:
        print("❌ 请求超时，转录可能需要更长时间")
        
    except requests.exceptions.ConnectionError:
        print("❌ 无法连接到API服务，请确保服务正在运行")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
    
    print("\n" + "=" * 60)
    print("测试完成")


if __name__ == "__main__":
    test_user_video_transcription()