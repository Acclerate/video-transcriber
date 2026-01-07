"""
简单的API测试脚本
测试现有cookies是否能处理用户的抖音视频
"""

import asyncio
import aiohttp
import json


async def test_video_api():
    """测试视频转录API"""
    
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
    
    print(f"🎯 测试视频链接: {user_video_url}")
    print("🚀 发送转录请求...")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "http://localhost:8000/api/v1/transcribe",
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=300)
            ) as response:
                
                status = response.status
                text = await response.text()
                
                print(f"📊 响应状态: {status}")
                
                if status == 200:
                    try:
                        data = json.loads(text)
                        print("✅ 转录请求成功！")
                        print(f"📄 响应代码: {data.get('code', 'N/A')}")
                        print(f"📝 响应消息: {data.get('message', 'N/A')}")
                        
                        if 'data' in data:
                            result_data = data['data']
                            if 'transcription' in result_data:
                                transcription = result_data['transcription']
                                print(f"📜 转录文本: {transcription.get('text', 'N/A')}")
                                print(f"🌍 识别语言: {transcription.get('language', 'N/A')}")
                                print(f"💯 置信度: {transcription.get('confidence', 'N/A')}")
                        
                        return True
                        
                    except json.JSONDecodeError as e:
                        print(f"❌ JSON解析失败: {e}")
                        print(f"📄 原始响应: {text}")
                        return False
                else:
                    print(f"❌ 请求失败: {text}")
                    return False
                    
    except Exception as e:
        print(f"❌ 请求异常: {e}")
        return False


async def test_cookies_api():
    """测试cookies相关API"""
    print("🍪 检查当前cookies状态...")
    
    try:
        async with aiohttp.ClientSession() as session:
            # 检查cookies信息
            async with session.get("http://localhost:8000/api/v1/cookies/info") as response:
                if response.status == 200:
                    data = await response.json()
                    cookies_info = data['data']
                    print(f"   📊 Cookies存在: {cookies_info['exists']}")
                    print(f"   ✅ Cookies有效: {cookies_info['valid']}")
                    print(f"   📁 文件大小: {cookies_info['size']} bytes")
                    print(f"   🔢 Cookie数量: {cookies_info['cookie_count']}")
                    print(f"   🔑 关键Cookies: {cookies_info['critical_cookies']}")
                    return cookies_info['valid']
                else:
                    print(f"   ❌ 获取cookies信息失败: {response.status}")
                    return False
    except Exception as e:
        print(f"   ❌ cookies API测试失败: {e}")
        return False


async def main():
    print("🔍 抖音视频转录功能测试")
    print("=" * 50)
    
    # 1. 检查cookies状态
    cookies_valid = await test_cookies_api()
    
    print()
    
    # 2. 测试视频转录
    if cookies_valid:
        print("✨ Cookies有效，开始测试视频转录...")
        success = await test_video_api()
        
        if success:
            print("\n🎉 测试成功！现有的cookies足以处理抖音视频")
        else:
            print("\n⚠️ 转录失败，可能需要更新cookies")
    else:
        print("❌ Cookies无效，需要重新登录获取新cookies")
    
    print("\n💡 如果需要更新cookies，请:")
    print("   1. 访问 http://localhost:8000")
    print("   2. 点击'开始扫码登录'")
    print("   3. 使用抖音APP扫描二维码登录")


if __name__ == "__main__":
    asyncio.run(main())