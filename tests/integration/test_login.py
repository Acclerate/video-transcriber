#!/usr/bin/env python3
"""
抖音扫码登录完整功能测试
验证从启动到获取cookies的完整流程
"""

import asyncio
import json
import time
import websockets
import requests
from pathlib import Path
from loguru import logger

# 配置日志
logger.add("logs/douyin_login_test.log", rotation="1 MB", level="INFO")

class DouyinLoginTester:
    """抖音扫码登录测试器"""
    
    def __init__(self, api_base="http://127.0.0.1:8000"):
        self.api_base = api_base
        self.ws_url = "ws://127.0.0.1:8000/ws/auth/douyin"
        self.test_results = []
    
    def test_api_endpoints(self):
        """测试API端点"""
        logger.info("=== 测试API端点 ===")
        
        # 1. 测试健康检查
        try:
            response = requests.get(f"{self.api_base}/health")
            if response.status_code == 200:
                logger.success("✅ 健康检查通过")
                self.test_results.append("健康检查: 通过")
            else:
                logger.error("❌ 健康检查失败")
                self.test_results.append("健康检查: 失败")
        except Exception as e:
            logger.error(f"❌ 健康检查异常: {e}")
            self.test_results.append(f"健康检查: 异常 - {e}")
        
        # 2. 测试登录状态查询
        try:
            response = requests.get(f"{self.api_base}/api/v1/auth/douyin/status")
            if response.status_code == 200:
                data = response.json()
                logger.success(f"✅ 登录状态查询成功: {data['data']}")
                self.test_results.append(f"登录状态查询: 成功 - {data['data']}")
            else:
                logger.error("❌ 登录状态查询失败")
                self.test_results.append("登录状态查询: 失败")
        except Exception as e:
            logger.error(f"❌ 登录状态查询异常: {e}")
            self.test_results.append(f"登录状态查询: 异常 - {e}")
        
        # 3. 测试Cookies信息查询
        try:
            response = requests.get(f"{self.api_base}/api/v1/cookies/info")
            if response.status_code == 200:
                data = response.json()
                logger.success(f"✅ Cookies信息查询成功: {data['data']}")
                self.test_results.append(f"Cookies信息查询: 成功")
            else:
                logger.error("❌ Cookies信息查询失败")
                self.test_results.append("Cookies信息查询: 失败")
        except Exception as e:
            logger.error(f"❌ Cookies信息查询异常: {e}")
            self.test_results.append(f"Cookies信息查询: 异常 - {e}")
        
        # 4. 测试启动扫码登录
        try:
            response = requests.post(f"{self.api_base}/api/v1/auth/douyin/start")
            if response.status_code == 200:
                data = response.json()
                logger.success(f"✅ 启动扫码登录成功: {data['message']}")
                self.test_results.append("启动扫码登录: 成功")
            else:
                logger.error("❌ 启动扫码登录失败")
                self.test_results.append("启动扫码登录: 失败")
        except Exception as e:
            logger.error(f"❌ 启动扫码登录异常: {e}")
            self.test_results.append(f"启动扫码登录: 异常 - {e}")
    
    async def test_websocket_login(self, timeout=30):
        """测试WebSocket扫码登录流程"""
        logger.info("=== 测试WebSocket扫码登录 ===")
        
        try:
            # 连接WebSocket
            logger.info(f"连接WebSocket: {self.ws_url}")
            async with websockets.connect(self.ws_url) as websocket:
                logger.success("✅ WebSocket连接成功")
                self.test_results.append("WebSocket连接: 成功")
                
                # 启动登录流程
                await websocket.send(json.dumps({"action": "start"}))
                logger.info("📤 发送启动登录请求")
                
                # 监听消息
                start_time = time.time()
                qr_code_received = False
                
                while time.time() - start_time < timeout:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                        data = json.loads(message)
                        
                        status = data.get('status', 'unknown')
                        logger.info(f"📥 收到状态更新: {status}")
                        
                        if status == 'qr_generated':
                            qr_code_received = True
                            qr_data = data.get('qr_code', {})
                            logger.success("✅ 二维码生成成功")
                            logger.info(f"二维码信息: 大小={len(qr_data.get('image_data', ''))}")
                            self.test_results.append("二维码生成: 成功")
                            
                            # 保存二维码（可选）
                            await self._save_qr_code(qr_data.get('image_data'))
                            
                        elif status == 'waiting_scan':
                            logger.info("⏳ 等待用户扫码...")
                            self.test_results.append("等待扫码: 进行中")
                            
                        elif status == 'scanned':
                            logger.info("📱 用户已扫码，等待确认...")
                            self.test_results.append("扫码确认: 等待中")
                            
                        elif status == 'success':
                            logger.success("🎉 登录成功！")
                            cookies = data.get('cookies', {})
                            logger.info(f"获取到cookies: {len(cookies)}个")
                            self.test_results.append("登录完成: 成功")
                            break
                            
                        elif status == 'failed':
                            logger.error(f"❌ 登录失败: {data.get('message', '未知错误')}")
                            self.test_results.append(f"登录失败: {data.get('message', '未知错误')}")
                            break
                            
                        elif status == 'timeout':
                            logger.warning("⏰ 登录超时")
                            self.test_results.append("登录超时: 是")
                            break
                        
                    except asyncio.TimeoutError:
                        continue
                    except Exception as e:
                        logger.error(f"❌ 处理消息异常: {e}")
                        continue
                
                if not qr_code_received:
                    logger.error("❌ 未收到二维码")
                    self.test_results.append("二维码生成: 失败")
                
        except Exception as e:
            logger.error(f"❌ WebSocket测试异常: {e}")
            self.test_results.append(f"WebSocket测试: 异常 - {e}")
    
    async def _save_qr_code(self, qr_data):
        """保存二维码图片"""
        if not qr_data or not qr_data.startswith('data:image/'):
            return
        
        try:
            import base64
            # 提取base64数据
            base64_data = qr_data.split(',')[1]
            image_data = base64.b64decode(base64_data)
            
            # 保存到文件
            qr_file = Path("temp/douyin_qr_code.png")
            qr_file.parent.mkdir(exist_ok=True)
            
            with open(qr_file, 'wb') as f:
                f.write(image_data)
            
            logger.info(f"💾 二维码已保存到: {qr_file}")
            
        except Exception as e:
            logger.warning(f"保存二维码失败: {e}")
    
    def check_cookies_file(self):
        """检查cookies文件"""
        logger.info("=== 检查Cookies文件 ===")
        
        cookies_file = Path("cookies.txt")
        if cookies_file.exists():
            size = cookies_file.stat().st_size
            mtime = time.ctime(cookies_file.stat().st_mtime)
            logger.success(f"✅ Cookies文件存在: 大小={size}字节, 修改时间={mtime}")
            self.test_results.append(f"Cookies文件: 存在({size}字节)")
            
            # 读取内容
            try:
                with open(cookies_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                    lines = [line.strip() for line in content.split('\n') if line.strip() and not line.startswith('#')]
                    logger.info(f"Cookies条目数: {len(lines)}")
                    self.test_results.append(f"Cookies条目数: {len(lines)}")
            except Exception as e:
                logger.warning(f"读取cookies文件失败: {e}")
        else:
            logger.warning("⚠️ Cookies文件不存在")
            self.test_results.append("Cookies文件: 不存在")
    
    def generate_report(self):
        """生成测试报告"""
        logger.info("=== 生成测试报告 ===")
        
        report = f"""
# 抖音扫码登录功能测试报告

## 测试时间
{time.strftime('%Y-%m-%d %H:%M:%S')}

## 测试结果
"""
        
        for i, result in enumerate(self.test_results, 1):
            report += f"{i}. {result}\n"
        
        report += f"""
## 总结
- 总测试项: {len(self.test_results)}
- 成功项数: {len([r for r in self.test_results if '成功' in r or '通过' in r])}
- 失败项数: {len([r for r in self.test_results if '失败' in r or '异常' in r])}

## 建议
1. 如果二维码生成成功，请使用抖音APP扫码测试完整流程
2. 确保网络连接稳定，避免登录超时
3. 定期更新cookies以保持有效性
"""
        
        # 保存报告
        report_file = Path("test_douyin_login_report.md")
        with open(report_file, 'w', encoding='utf-8') as f:
            f.write(report)
        
        logger.success(f"📋 测试报告已保存到: {report_file}")
        print(report)


async def main():
    """主测试函数"""
    logger.info("🚀 开始抖音扫码登录功能测试")
    
    tester = DouyinLoginTester()
    
    # 1. 测试API端点
    tester.test_api_endpoints()
    
    # 2. 检查cookies文件
    tester.check_cookies_file()
    
    # 3. 测试WebSocket扫码登录（可选）
    print("\n" + "="*50)
    choice = input("是否要测试WebSocket扫码登录流程？(y/n): ").lower().strip()
    
    if choice == 'y':
        print("⚠️ 注意：这将启动真实的扫码登录流程")
        print("请准备好抖音APP进行扫码")
        input("按回车键继续...")
        
        await tester.test_websocket_login(timeout=60)
    else:
        logger.info("跳过WebSocket扫码登录测试")
        tester.test_results.append("WebSocket扫码登录: 跳过")
    
    # 4. 生成测试报告
    tester.generate_report()
    
    logger.success("🎯 测试完成！")


if __name__ == "__main__":
    # 确保logs目录存在
    Path("logs").mkdir(exist_ok=True)
    Path("temp").mkdir(exist_ok=True)
    
    # 运行测试
    asyncio.run(main())