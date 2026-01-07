"""
抖音扫码登录实际功能测试
测试与Web服务器的完整交互
"""

import asyncio
import json
import websockets
import aiohttp
from datetime import datetime


async def test_rest_apis():
    """测试REST API接口"""
    print("🔌 测试REST API接口...")
    
    base_url = "http://localhost:8000"
    
    async with aiohttp.ClientSession() as session:
        try:
            # 1. 测试健康检查
            print("   🏥 测试健康检查API...")
            async with session.get(f"{base_url}/health") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"      ✅ 健康检查: {data['status']}")
                else:
                    print(f"      ❌ 健康检查失败: {response.status}")
            
            # 2. 测试抖音认证状态
            print("   📊 测试抖音认证状态API...")
            async with session.get(f"{base_url}/api/v1/auth/douyin/status") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"      ✅ 认证状态: {data['data']['status']}")
                    print(f"      🍪 Cookies存在: {data['data']['cookies_exists']}")
                else:
                    print(f"      ❌ 状态查询失败: {response.status}")
            
            # 3. 测试Cookies信息
            print("   🍪 测试Cookies信息API...")
            async with session.get(f"{base_url}/api/v1/cookies/info") as response:
                if response.status == 200:
                    data = await response.json()
                    cookies_data = data['data']
                    print(f"      ✅ Cookies有效性: {cookies_data['valid']}")
                    print(f"      📁 文件大小: {cookies_data['size']} bytes")
                    print(f"      🔢 Cookie数量: {cookies_data['cookie_count']}")
                    print(f"      🔑 关键Cookies: {cookies_data['critical_cookies']}")
                else:
                    print(f"      ❌ Cookies信息查询失败: {response.status}")
            
            # 4. 测试Cookies验证
            print("   🔒 测试Cookies验证API...")
            async with session.get(f"{base_url}/api/v1/cookies/validate") as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"      ✅ 验证结果: {data['data']['message']}")
                else:
                    print(f"      ❌ Cookies验证失败: {response.status}")
            
            return True
            
        except Exception as e:
            print(f"   ❌ REST API测试失败: {e}")
            return False


async def test_websocket_connection():
    """测试WebSocket连接"""
    print("\n📡 测试WebSocket连接...")
    
    try:
        websocket_url = "ws://localhost:8000/ws/auth/douyin"
        
        print(f"   🔗 连接到: {websocket_url}")
        
        async with websockets.connect(websocket_url) as websocket:
            print("   ✅ WebSocket连接成功")
            
            # 等待接收消息
            print("   📨 等待接收消息...")
            
            message_count = 0
            start_time = asyncio.get_event_loop().time()
            timeout = 30  # 30秒超时
            
            try:
                while True:
                    # 设置超时
                    current_time = asyncio.get_event_loop().time()
                    if current_time - start_time > timeout:
                        print("   ⏰ 测试超时，结束监听")
                        break
                    
                    # 接收消息（设置较短的超时）
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=5.0)
                        message_count += 1
                        
                        try:
                            data = json.loads(message)
                            msg_type = data.get('type', 'unknown')
                            status = data.get('status', 'N/A')
                            msg_text = data.get('message', 'N/A')
                            
                            print(f"   📨 消息 #{message_count}:")
                            print(f"       类型: {msg_type}")
                            print(f"       状态: {status}")
                            print(f"       消息: {msg_text}")
                            
                            # 如果收到二维码
                            if data.get('qr_code'):
                                qr_data = data['qr_code']
                                qr_length = len(qr_data) if qr_data else 0
                                print(f"       🔲 二维码数据长度: {qr_length} 字符")
                                
                                # 保存二维码到文件
                                if qr_data and qr_data.startswith('data:image'):
                                    try:
                                        import base64
                                        # 提取base64数据
                                        base64_data = qr_data.split(',')[1]
                                        qr_bytes = base64.b64decode(base64_data)
                                        
                                        with open('qr_code_test.png', 'wb') as f:
                                            f.write(qr_bytes)
                                        print(f"       💾 二维码已保存到: qr_code_test.png")
                                    except Exception as e:
                                        print(f"       ❌ 保存二维码失败: {e}")
                            
                            # 如果是登录结果
                            if msg_type == 'login_result':
                                cookies_count = data.get('cookies_count', 0)
                                print(f"       🍪 获取到 {cookies_count} 个cookies")
                                
                                if status == 'success':
                                    print("       🎉 登录成功！")
                                    break
                                elif status in ['failed', 'timeout']:
                                    print(f"       ❌ 登录失败: {status}")
                                    break
                            
                        except json.JSONDecodeError:
                            print(f"   📨 原始消息: {message}")
                    
                    except asyncio.TimeoutError:
                        # 超时是正常的，继续监听
                        continue
                    
                    # 限制消息数量
                    if message_count >= 20:
                        print("   📊 已接收足够多的消息，结束测试")
                        break
            
            except websockets.exceptions.ConnectionClosed:
                print("   🔌 WebSocket连接已关闭")
            
            print(f"   📊 总共接收到 {message_count} 条消息")
            
            if message_count > 0:
                print("   ✅ WebSocket通信正常")
                return True
            else:
                print("   ⚠️ 未接收到任何消息")
                return False
        
    except Exception as e:
        print(f"   ❌ WebSocket测试失败: {e}")
        return False


async def test_douyin_video_with_existing_cookies():
    """测试使用现有cookies处理抖音视频"""
    print("\n🎥 测试使用现有cookies处理抖音视频...")
    
    try:
        # 用户提供的抖音视频链接
        test_url = "https://v.douyin.com/wrvKzCqdS5k/"
        
        base_url = "http://localhost:8000"
        
        async with aiohttp.ClientSession() as session:
            # 构造转录请求
            request_data = {
                "url": test_url,
                "options": {
                    "model": "small",
                    "language": "auto",
                    "with_timestamps": True,
                    "output_format": "json",
                    "enable_gpu": True,
                    "temperature": 0.0
                }
            }
            
            print(f"   🔗 测试视频: {test_url}")
            print("   🚀 发送转录请求...")
            
            async with session.post(
                f"{base_url}/api/v1/transcribe",
                json=request_data,
                timeout=aiohttp.ClientTimeout(total=300)  # 5分钟超时
            ) as response:
                
                print(f"   📊 响应状态: {response.status}")
                
                if response.status == 200:
                    data = await response.json()
                    print("   ✅ 转录请求成功提交")
                    print(f"   📄 响应代码: {data.get('code', 'N/A')}")
                    print(f"   📝 响应消息: {data.get('message', 'N/A')}")
                    
                    # 检查转录结果
                    if 'data' in data and 'transcription' in data['data']:
                        transcription = data['data']['transcription']
                        print(f"   📜 转录文本: {transcription.get('text', 'N/A')}")
                        print(f"   🌍 识别语言: {transcription.get('language', 'N/A')}")
                        print(f"   💯 置信度: {transcription.get('confidence', 'N/A')}")
                    
                    return True
                else:
                    response_text = await response.text()
                    print(f"   ❌ 转录请求失败: {response_text}")
                    return False
    
    except Exception as e:
        print(f"   ❌ 视频转录测试失败: {e}")
        return False


async def main():
    """主测试函数"""
    print("🚀 抖音扫码登录实际功能测试开始")
    print(f"⏰ 测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    test_results = []
    
    # 测试项目
    tests = [
        ("REST API接口", test_rest_apis),
        ("WebSocket连接", test_websocket_connection),
        ("现有Cookies视频处理", test_douyin_video_with_existing_cookies)
    ]
    
    for test_name, test_func in tests:
        try:
            print(f"\n🧪 执行测试: {test_name}")
            result = await test_func()
            test_results.append((test_name, result))
        except Exception as e:
            print(f"   💥 测试崩溃: {e}")
            test_results.append((test_name, False))
    
    # 汇总结果
    print("\n" + "=" * 70)
    print("📊 实际功能测试结果汇总:")
    
    passed = 0
    total = len(test_results)
    
    for test_name, result in test_results:
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {status} {test_name}")
        if result:
            passed += 1
    
    print(f"\n🎯 总体结果: {passed}/{total} 项测试通过")
    
    if passed >= 2:  # WebSocket测试可能因为没有实际扫码而超时
        print("🎉 扫码登录功能基本正常！")
        print("\n📱 手动测试建议:")
        print("   1. 访问 http://localhost:8000 查看Web界面")
        print("   2. 点击'开始扫码登录'按钮")
        print("   3. 使用抖音APP扫描生成的二维码")
        print("   4. 在手机上确认登录")
        print("   5. 观察cookies是否成功更新")
    else:
        print("⚠️ 部分功能需要检查")
    
    print("\n💡 测试完成提示:")
    print("   - 服务器仍在运行，可以进行手动测试")
    print("   - 使用 Ctrl+C 停止服务器")
    print("   - 如果生成了二维码，请检查 qr_code_test.png 文件")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n⏹️ 测试被用户中断")
    except Exception as e:
        print(f"\n💥 测试执行失败: {e}")