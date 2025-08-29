"""
抖音扫码登录功能测试

测试抖音扫码登录模块的各项功能和错误处理。
"""

import pytest
import asyncio
from unittest.mock import Mock, patch, AsyncMock
from pathlib import Path
import tempfile
import json

from core.douyin_auth import DouyinAuthenticator, LoginStatus, QRCodeInfo, LoginResult
from core.cookie_manager import CookieManager


class TestDouyinAuthenticator:
    """抖音认证器测试"""
    
    @pytest.fixture
    async def authenticator(self):
        """创建认证器实例"""
        auth = DouyinAuthenticator()
        yield auth
        # 清理
        await auth.stop()
    
    @pytest.fixture
    def mock_playwright(self):
        """模拟Playwright"""
        with patch('core.douyin_auth.async_playwright') as mock:
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock.return_value.start.return_value.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            yield {
                'playwright': mock,
                'browser': mock_browser,
                'context': mock_context,
                'page': mock_page
            }
    
    @pytest.mark.asyncio
    async def test_initialize_success(self, authenticator, mock_playwright):
        """测试浏览器初始化成功"""
        result = await authenticator.initialize()
        
        assert result is True
        assert authenticator.status == LoginStatus.INITIALIZING
        assert authenticator.browser is not None
    
    @pytest.mark.asyncio
    async def test_initialize_playwright_not_installed(self, authenticator):
        """测试Playwright未安装的情况"""
        with patch('core.douyin_auth.async_playwright', None):
            result = await authenticator.initialize()
            
            assert result is False
    
    @pytest.mark.asyncio
    async def test_start_login_flow(self, authenticator, mock_playwright):
        """测试启动登录流程"""
        # 模拟页面元素
        mock_playwright['page'].query_selector.return_value = AsyncMock()
        mock_playwright['page'].query_selector.return_value.screenshot.return_value = b'fake_image_data'
        
        with patch.object(authenticator, '_monitor_login_status') as mock_monitor:
            mock_monitor.return_value = LoginResult(
                status=LoginStatus.SUCCESS,
                cookies={'sessionid': 'test_session'},
                message="登录成功"
            )
            
            result = await authenticator.start_login()
            
            assert result.status == LoginStatus.SUCCESS
            assert result.cookies is not None
    
    @pytest.mark.asyncio
    async def test_get_qr_code_success(self, authenticator, mock_playwright):
        """测试获取二维码成功"""
        # 模拟页面元素
        mock_element = AsyncMock()
        mock_element.screenshot.return_value = b'fake_qr_data'
        mock_playwright['page'].query_selector.return_value = mock_element
        
        # 初始化并设置页面
        await authenticator.initialize()
        
        qr_code = await authenticator._get_qr_code()
        
        assert qr_code is not None
        assert isinstance(qr_code, QRCodeInfo)
        assert qr_code.image_data.startswith('data:image/png;base64,')
    
    @pytest.mark.asyncio
    async def test_get_qr_code_not_found(self, authenticator, mock_playwright):
        """测试未找到二维码元素"""
        # 模拟未找到元素
        mock_playwright['page'].query_selector.return_value = None
        
        await authenticator.initialize()
        qr_code = await authenticator._get_qr_code()
        
        assert qr_code is None
    
    @pytest.mark.asyncio
    async def test_check_login_success(self, authenticator, mock_playwright):
        """测试检查登录成功"""
        # 模拟页面URL变化
        mock_playwright['page'].url = "https://www.douyin.com/user/123"
        
        await authenticator.initialize()
        result = await authenticator._check_login_success()
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_extract_cookies(self, authenticator, mock_playwright):
        """测试提取cookies"""
        # 模拟cookies数据
        mock_cookies = [
            {'name': 'sessionid', 'value': 'test_session', 'domain': '.douyin.com'},
            {'name': 's_v_web_id', 'value': 'test_web_id', 'domain': '.douyin.com'},
            {'name': 'other_cookie', 'value': 'other_value', 'domain': '.example.com'}
        ]
        
        await authenticator.initialize()
        mock_playwright['context'].cookies.return_value = mock_cookies
        
        cookies = await authenticator._extract_cookies()
        
        assert cookies is not None
        assert 'sessionid' in cookies
        assert 's_v_web_id' in cookies
        assert 'other_cookie' not in cookies  # 应该过滤掉非抖音域名的cookies
    
    @pytest.mark.asyncio
    async def test_save_cookies(self, authenticator):
        """测试保存cookies"""
        cookies = {
            'sessionid': 'test_session',
            's_v_web_id': 'test_web_id'
        }
        
        with tempfile.TemporaryDirectory() as temp_dir:
            # 设置临时cookies文件路径
            authenticator.cookies_file = Path(temp_dir) / "test_cookies.txt"
            
            result = await authenticator._save_cookies(cookies)
            
            assert result is True
            assert authenticator.cookies_file.exists()
            
            # 验证文件内容
            content = authenticator.cookies_file.read_text()
            assert 'sessionid' in content
            assert 's_v_web_id' in content
    
    @pytest.mark.asyncio
    async def test_stop_cleanup(self, authenticator, mock_playwright):
        """测试停止和清理资源"""
        await authenticator.initialize()
        await authenticator.stop()
        
        assert authenticator.status == LoginStatus.STOPPED
        mock_playwright['page'].close.assert_called_once()
        mock_playwright['context'].close.assert_called_once()
        mock_playwright['browser'].close.assert_called_once()


class TestCookieManager:
    """Cookie管理器测试"""
    
    @pytest.fixture
    def cookie_manager(self):
        """创建Cookie管理器实例"""
        with tempfile.TemporaryDirectory() as temp_dir:
            manager = CookieManager()
            manager.cookies_file = Path(temp_dir) / "test_cookies.txt"
            manager.backup_dir = Path(temp_dir) / "backups"
            manager.backup_dir.mkdir(exist_ok=True)
            yield manager
    
    def test_is_cookies_valid_file_not_exists(self, cookie_manager):
        """测试cookies文件不存在"""
        result = cookie_manager.is_cookies_valid()
        assert result is False
    
    def test_is_cookies_valid_empty_file(self, cookie_manager):
        """测试空cookies文件"""
        cookie_manager.cookies_file.touch()
        result = cookie_manager.is_cookies_valid()
        assert result is False
    
    def test_is_cookies_valid_valid_cookies(self, cookie_manager):
        """测试有效cookies文件"""
        valid_cookies = '''# Netscape HTTP Cookie File
.douyin.com\tTRUE\t/\tFALSE\t0\tsessionid\ttest_session
.douyin.com\tTRUE\t/\tFALSE\t0\ts_v_web_id\ttest_web_id'''
        
        cookie_manager.cookies_file.write_text(valid_cookies)
        result = cookie_manager.is_cookies_valid()
        assert result is True
    
    def test_parse_cookies_file(self, cookie_manager):
        """测试解析cookies文件"""
        cookies_content = '''# Netscape HTTP Cookie File
.douyin.com\tTRUE\t/\tFALSE\t0\tsessionid\ttest_session
.douyin.com\tTRUE\t/\tFALSE\t0\ts_v_web_id\ttest_web_id
# 这是注释行
invalid_line_format'''
        
        cookie_manager.cookies_file.write_text(cookies_content)
        cookies = cookie_manager.parse_cookies_file()
        
        assert len(cookies) == 2
        assert cookies['sessionid'] == 'test_session'
        assert cookies['s_v_web_id'] == 'test_web_id'
    
    def test_get_critical_cookies(self, cookie_manager):
        """测试获取关键cookies"""
        cookies_content = '''# Netscape HTTP Cookie File
.douyin.com\tTRUE\t/\tFALSE\t0\tsessionid\ttest_session
.douyin.com\tTRUE\t/\tFALSE\t0\ts_v_web_id\ttest_web_id
.douyin.com\tTRUE\t/\tFALSE\t0\tother_cookie\tother_value'''
        
        cookie_manager.cookies_file.write_text(cookies_content)
        critical_cookies = cookie_manager.get_critical_cookies()
        
        assert 'sessionid' in critical_cookies
        assert 's_v_web_id' in critical_cookies
        assert 'other_cookie' not in critical_cookies
    
    def test_backup_cookies(self, cookie_manager):
        """测试备份cookies"""
        # 创建cookies文件
        cookie_manager.cookies_file.write_text("test cookies content")
        
        result = cookie_manager.backup_cookies()
        
        assert result is True
        # 验证备份文件是否创建
        backup_files = list(cookie_manager.backup_dir.glob("cookies_backup_*.txt"))
        assert len(backup_files) > 0
    
    def test_update_cookies_from_dict(self, cookie_manager):
        """测试从字典更新cookies"""
        cookies_dict = {
            'sessionid': 'new_session',
            's_v_web_id': 'new_web_id'
        }
        
        result = cookie_manager.update_cookies_from_dict(cookies_dict)
        
        assert result is True
        assert cookie_manager.cookies_file.exists()
        
        # 验证文件内容
        content = cookie_manager.cookies_file.read_text()
        assert 'sessionid\tnew_session' in content
        assert 's_v_web_id\tnew_web_id' in content
    
    def test_get_cookie_info(self, cookie_manager):
        """测试获取cookie信息"""
        # 创建有效的cookies文件
        cookies_content = '''# Netscape HTTP Cookie File
.douyin.com\tTRUE\t/\tFALSE\t0\tsessionid\ttest_session
.douyin.com\tTRUE\t/\tFALSE\t0\ts_v_web_id\ttest_web_id'''
        
        cookie_manager.cookies_file.write_text(cookies_content)
        
        info = cookie_manager.get_cookie_info()
        
        assert info['exists'] is True
        assert info['valid'] is True
        assert info['cookie_count'] == 2
        assert info['critical_cookies'] == 2
        assert info['size'] > 0
    
    def test_validate_cookie_format(self, cookie_manager):
        """测试验证cookie格式"""
        valid_format = '''.douyin.com\tTRUE\t/\tFALSE\t0\tsessionid\ttest_session'''
        invalid_format = '''invalid format'''
        
        assert cookie_manager.validate_cookie_format(valid_format) is True
        assert cookie_manager.validate_cookie_format(invalid_format) is False
    
    def test_cleanup_old_backups(self, cookie_manager):
        """测试清理旧备份"""
        # 创建多个备份文件
        for i in range(15):
            backup_file = cookie_manager.backup_dir / f"cookies_backup_202312{i:02d}_120000.txt"
            backup_file.write_text(f"backup {i}")
        
        cleaned_count = cookie_manager.cleanup_old_backups(keep_count=10)
        
        assert cleaned_count == 5
        remaining_files = list(cookie_manager.backup_dir.glob("cookies_backup_*.txt"))
        assert len(remaining_files) == 10


class TestIntegration:
    """集成测试"""
    
    @pytest.mark.asyncio
    async def test_full_login_flow_mock(self):
        """测试完整的登录流程（模拟）"""
        with patch('core.douyin_auth.async_playwright') as mock_playwright:
            # 设置模拟对象
            mock_browser = AsyncMock()
            mock_context = AsyncMock()
            mock_page = AsyncMock()
            
            mock_playwright.return_value.start.return_value.chromium.launch.return_value = mock_browser
            mock_browser.new_context.return_value = mock_context
            mock_context.new_page.return_value = mock_page
            
            # 模拟二维码元素
            mock_qr_element = AsyncMock()
            mock_qr_element.screenshot.return_value = b'fake_qr_data'
            mock_page.query_selector.return_value = mock_qr_element
            
            # 模拟登录成功
            mock_page.url = "https://www.douyin.com/user/123"
            mock_context.cookies.return_value = [
                {'name': 'sessionid', 'value': 'test_session', 'domain': '.douyin.com'}
            ]
            
            # 创建认证器并测试
            authenticator = DouyinAuthenticator()
            
            try:
                # 模拟快速登录成功
                with patch.object(authenticator, '_monitor_login_status') as mock_monitor:
                    mock_monitor.return_value = LoginResult(
                        status=LoginStatus.SUCCESS,
                        cookies={'sessionid': 'test_session'},
                        message="登录成功"
                    )
                    
                    result = await authenticator.start_login()
                    
                    assert result.status == LoginStatus.SUCCESS
                    assert result.cookies is not None
                    assert 'sessionid' in result.cookies
            
            finally:
                await authenticator.stop()
    
    @pytest.mark.asyncio
    async def test_error_handling(self):
        """测试错误处理"""
        authenticator = DouyinAuthenticator()
        
        # 测试在未初始化状态下调用方法
        result = await authenticator._get_qr_code()
        assert result is None
        
        # 测试文件保存错误
        with patch('builtins.open', side_effect=PermissionError()):
            cookies = {'test': 'value'}
            result = await authenticator._save_cookies(cookies)
            assert result is False


if __name__ == "__main__":
    # 运行测试
    pytest.main([__file__, "-v"])