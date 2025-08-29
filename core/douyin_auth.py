"""
抖音扫码登录自动化模块

该模块使用Playwright实现抖音扫码登录功能，自动获取登录后的cookies信息。
"""

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from enum import Enum

try:
    from playwright.async_api import async_playwright, Browser, BrowserContext, Page
except ImportError:
    async_playwright = None
    Browser = None
    BrowserContext = None
    Page = None

from utils.logger import get_logger

logger = get_logger(__name__)


class LoginStatus(Enum):
    """登录状态枚举"""
    IDLE = "idle"                    # 空闲状态
    INITIALIZING = "initializing"    # 初始化中
    QR_GENERATED = "qr_generated"    # 二维码已生成
    WAITING_SCAN = "waiting_scan"    # 等待扫码
    SCANNED = "scanned"              # 已扫码，等待确认
    SUCCESS = "success"              # 登录成功
    FAILED = "failed"                # 登录失败
    TIMEOUT = "timeout"              # 超时
    STOPPED = "stopped"              # 已停止


@dataclass
class QRCodeInfo:
    """二维码信息"""
    image_data: str  # base64编码的图片数据
    refresh_time: float  # 生成时间
    expires_in: int = 300  # 过期时间(秒)


@dataclass
class LoginResult:
    """登录结果"""
    status: LoginStatus
    cookies: Optional[Dict[str, Any]] = None
    message: str = ""
    qr_code: Optional[QRCodeInfo] = None


class DouyinAuthenticator:
    """抖音扫码登录认证器"""
    
    def __init__(self):
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.playwright = None
        
        self.status = LoginStatus.IDLE
        self.callbacks: Dict[str, Callable] = {}
        self.cookies_file = Path("./cookies.txt")
        
        # 登录相关配置
        self.login_url = "https://www.douyin.com/passport/web/login/"
        self.timeout = 300  # 5分钟超时
        self.check_interval = 2  # 检查间隔(秒)
    
    async def initialize(self) -> bool:
        """初始化浏览器"""
        if async_playwright is None:
            logger.error("Playwright未安装，请运行: pip install playwright && playwright install")
            return False
            
        try:
            self.status = LoginStatus.INITIALIZING
            self._notify_status_change()
            
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=True,  # 可以设置为False进行调试
                args=[
                    '--no-sandbox',
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                ]
            )
            
            self.context = await self.browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            
            self.page = await self.context.new_page()
            logger.info("浏览器初始化成功")
            return True
            
        except Exception as e:
            logger.error(f"浏览器初始化失败: {e}")
            self.status = LoginStatus.FAILED
            self._notify_status_change()
            return False
    
    async def start_login(self) -> LoginResult:
        """启动扫码登录流程"""
        max_retries = 3
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                if not await self.initialize():
                    return LoginResult(
                        status=LoginStatus.FAILED,
                        message="浏览器初始化失败"
                    )
                
                # 访问登录页面
                logger.info("正在访问抖音登录页面...")
                try:
                    await self.page.goto(self.login_url, wait_until='networkidle', timeout=30000)
                except Exception as e:
                    logger.warning(f"页面加载超时，尝试继续: {e}")
                    # 等待页面部分加载
                    await asyncio.sleep(5)
                
                # 等待页面加载
                await asyncio.sleep(3)
                
                # 查找并点击扫码登录按钮
                qr_selectors = [
                    '[data-e2e="qrcode-tab"]',
                    '.qrcode-tab',
                    'text="扫码登录"',
                    'text="二维码登录"'
                ]
                
                qr_button = None
                for selector in qr_selectors:
                    try:
                        qr_button = await self.page.query_selector(selector)
                        if qr_button:
                            break
                    except Exception:
                        continue
                
                if qr_button:
                    try:
                        await qr_button.click()
                        await asyncio.sleep(2)
                        logger.info("已点击扫码登录按钮")
                    except Exception as e:
                        logger.warning(f"点击扫码按钮失败: {e}")
                
                # 获取二维码
                qr_code = await self._get_qr_code()
                if not qr_code:
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"获取二维码失败，第{retry_count}次重试...")
                        await self.stop()
                        await asyncio.sleep(2)
                        continue
                    else:
                        return LoginResult(
                            status=LoginStatus.FAILED,
                            message="无法获取二维码，请检查网络连接"
                        )
                
                self.status = LoginStatus.QR_GENERATED
                self._notify_status_change()
                
                # 开始监听登录状态
                result = await self._monitor_login_status()
                
                return LoginResult(
                    status=result.status,
                    cookies=result.cookies,
                    message=result.message,
                    qr_code=qr_code
                )
                
            except Exception as e:
                retry_count += 1
                logger.error(f"登录流程失败（第{retry_count}次）: {e}")
                
                if retry_count < max_retries:
                    await self.stop()
                    await asyncio.sleep(3)
                    continue
                else:
                    return LoginResult(
                        status=LoginStatus.FAILED,
                        message=f"登录失败（尝试{max_retries}次）: {str(e)}"
                    )
        
        return LoginResult(
            status=LoginStatus.FAILED,
            message="超出最大重试次数"
        )
    
    async def _get_qr_code(self) -> Optional[QRCodeInfo]:
        """获取二维码信息"""
        max_attempts = 5
        attempt = 0
        
        while attempt < max_attempts:
            try:
                attempt += 1
                logger.info(f"正在获取二维码（第{attempt}次尝试）...")
                
                # 等待二维码元素出现
                qr_selectors = [
                    'img[alt*="二维码"]',
                    'img[src*="qr"]', 
                    'img[class*="qr"]',
                    'canvas',
                    '.qrcode img',
                    '.login-qrcode img',
                    '[class*="qr"] img',
                    'img[class*="qrcode"]',
                    '.scan-qrcode img'
                ]
                
                qr_element = None
                for selector in qr_selectors:
                    try:
                        await self.page.wait_for_selector(selector, timeout=8000)
                        qr_element = await self.page.query_selector(selector)
                        if qr_element:
                            logger.info(f"找到二维码元素: {selector}")
                            break
                    except Exception:
                        continue
                
                if not qr_element:
                    # 尝试截取整个页面查找二维码区域
                    logger.warning("未找到二维码元素，尝试截取整个页面...")
                    try:
                        # 查找可能包含二维码的区域
                        qr_container_selectors = [
                            '.qrcode-container',
                            '.qr-container', 
                            '.login-qr',
                            '.scan-login',
                            '[class*="qrcode"]',
                            '[class*="scan"]'
                        ]
                        
                        for container_selector in qr_container_selectors:
                            container = await self.page.query_selector(container_selector)
                            if container:
                                qr_element = container
                                logger.info(f"找到二维码容器: {container_selector}")
                                break
                        
                        if not qr_element:
                            # 最后尝试：截取可视区域中央部分
                            qr_element = await self.page.query_selector('body')
                            
                    except Exception as e:
                        logger.warning(f"截取页面失败: {e}")
                
                if qr_element:
                    try:
                        # 获取图片的base64数据
                        image_data = await qr_element.screenshot(type='png')
                        if len(image_data) > 1000:  # 检查图片大小是否合理
                            base64_data = base64.b64encode(image_data).decode()
                            
                            logger.info("成功获取二维码")
                            return QRCodeInfo(
                                image_data=f"data:image/png;base64,{base64_data}",
                                refresh_time=time.time()
                            )
                        else:
                            logger.warning("二维码图片太小，可能无效")
                            
                    except Exception as e:
                        logger.warning(f"截取二维码失败: {e}")
                
                # 如果失败，等待一下再试
                if attempt < max_attempts:
                    logger.info(f"等待3秒后重试...")
                    await asyncio.sleep(3)
                    
                    # 尝试刷新页面
                    try:
                        await self.page.reload(wait_until='networkidle', timeout=15000)
                        await asyncio.sleep(2)
                        
                        # 重新点击扫码登录按钮
                        qr_button_selectors = [
                            '[data-e2e="qrcode-tab"]',
                            '.qrcode-tab',
                            'text="扫码登录"',
                            'text="二维码登录"'
                        ]
                        
                        for selector in qr_button_selectors:
                            try:
                                qr_button = await self.page.query_selector(selector)
                                if qr_button:
                                    await qr_button.click()
                                    await asyncio.sleep(2)
                                    break
                            except Exception:
                                continue
                                
                    except Exception as e:
                        logger.warning(f"刷新页面失败: {e}")
                
            except Exception as e:
                logger.error(f"获取二维码时出错（第{attempt}次）: {e}")
                if attempt < max_attempts:
                    await asyncio.sleep(2)
                    continue
        
        logger.error("无法获取二维码，已超出最大尝试次数")
        return None
    
    async def _monitor_login_status(self) -> LoginResult:
        """监听登录状态变化"""
        start_time = time.time()
        self.status = LoginStatus.WAITING_SCAN
        self._notify_status_change()
        
        while time.time() - start_time < self.timeout:
            try:
                # 检查是否已登录成功
                if await self._check_login_success():
                    cookies = await self._extract_cookies()
                    if cookies:
                        await self._save_cookies(cookies)
                        self.status = LoginStatus.SUCCESS
                        self._notify_status_change()
                        
                        return LoginResult(
                            status=LoginStatus.SUCCESS,
                            cookies=cookies,
                            message="登录成功，cookies已保存"
                        )
                
                # 检查是否已扫码但未确认
                if await self._check_scanned():
                    if self.status != LoginStatus.SCANNED:
                        self.status = LoginStatus.SCANNED
                        self._notify_status_change()
                
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"监听登录状态时出错: {e}")
                continue
        
        # 超时
        self.status = LoginStatus.TIMEOUT
        self._notify_status_change()
        return LoginResult(
            status=LoginStatus.TIMEOUT,
            message="登录超时，请重试"
        )
    
    async def _check_login_success(self) -> bool:
        """检查是否登录成功"""
        try:
            # 检查URL变化
            current_url = self.page.url
            if 'passport/web/login' not in current_url or 'douyin.com' in current_url:
                return True
            
            # 检查用户头像等登录后的元素
            user_elements = [
                '[data-e2e="user-avatar"]',
                '.avatar',
                '[class*="avatar"]',
                '.user-info'
            ]
            
            for selector in user_elements:
                element = await self.page.query_selector(selector)
                if element:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查登录状态失败: {e}")
            return False
    
    async def _check_scanned(self) -> bool:
        """检查是否已扫码"""
        try:
            # 查找扫码成功的提示文本
            scanned_texts = ["请在手机上确认", "扫描成功", "请确认登录"]
            
            for text in scanned_texts:
                element = await self.page.query_selector(f'text="{text}"')
                if element:
                    return True
            
            return False
            
        except Exception as e:
            logger.error(f"检查扫码状态失败: {e}")
            return False
    
    async def _extract_cookies(self) -> Optional[Dict[str, Any]]:
        """提取登录后的cookies"""
        try:
            if not self.context:
                return None
            
            # 获取所有cookies
            all_cookies = await self.context.cookies()
            
            # 筛选抖音相关的关键cookies
            douyin_cookies = {}
            important_cookies = [
                'sessionid', 'sessionid_ss', 's_v_web_id', 'ttwid', 
                'odin_tt', 'passport_csrf_token', 'passport_csrf_token_default',
                'sid_guard', 'uid_tt', 'uid_tt_ss', 'sid_tt', 'ssid_ucp_v1'
            ]
            
            for cookie in all_cookies:
                if any(domain in cookie.get('domain', '') for domain in ['.douyin.com', '.amemv.com', '.snssdk.com']):
                    if cookie['name'] in important_cookies:
                        douyin_cookies[cookie['name']] = cookie['value']
            
            if douyin_cookies:
                logger.info(f"成功提取{len(douyin_cookies)}个关键cookies")
                return douyin_cookies
            
            logger.warning("未找到关键cookies")
            return None
            
        except Exception as e:
            logger.error(f"提取cookies失败: {e}")
            return None
    
    async def _save_cookies(self, cookies: Dict[str, Any]) -> bool:
        """保存cookies到文件"""
        try:
            # 转换为Netscape格式
            cookie_lines = ['# Netscape HTTP Cookie File']
            
            for name, value in cookies.items():
                # 格式: domain, tailmatch, path, secure, expires, name, value
                line = f".douyin.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}"
                cookie_lines.append(line)
            
            # 保存到文件
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(cookie_lines))
            
            logger.info(f"Cookies已保存到: {self.cookies_file}")
            return True
            
        except Exception as e:
            logger.error(f"保存cookies失败: {e}")
            return False
    
    async def stop(self):
        """停止登录流程并清理资源"""
        try:
            self.status = LoginStatus.STOPPED
            self._notify_status_change()
            
            if self.page:
                await self.page.close()
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
            if self.playwright:
                await self.playwright.stop()
            
            logger.info("浏览器资源已清理")
            
        except Exception as e:
            logger.error(f"清理资源时出错: {e}")
    
    def add_callback(self, event: str, callback: Callable):
        """添加状态变化回调"""
        self.callbacks[event] = callback
    
    def _notify_status_change(self):
        """通知状态变化"""
        if 'status_change' in self.callbacks:
            try:
                self.callbacks['status_change'](self.status)
            except Exception as e:
                logger.error(f"回调函数执行失败: {e}")
    
    async def refresh_qr_code(self) -> Optional[QRCodeInfo]:
        """刷新二维码"""
        try:
            if self.page:
                await self.page.reload()
                await asyncio.sleep(3)
                return await self._get_qr_code()
            return None
        except Exception as e:
            logger.error(f"刷新二维码失败: {e}")
            return None


# 全局认证器实例
_authenticator: Optional[DouyinAuthenticator] = None


async def get_authenticator() -> DouyinAuthenticator:
    """获取认证器实例"""
    global _authenticator
    if _authenticator is None:
        _authenticator = DouyinAuthenticator()
    return _authenticator


async def cleanup_authenticator():
    """清理认证器实例"""
    global _authenticator
    if _authenticator:
        await _authenticator.stop()
        _authenticator = None