"""
Cookie管理模块

负责管理和验证抖音等平台的cookies，支持扫码登录集成。
"""

import os
import time
from pathlib import Path
from typing import Dict, Optional, List, Any
from datetime import datetime, timedelta

from utils.logger import get_logger

logger = get_logger(__name__)


class CookieManager:
    """Cookie管理器"""
    
    def __init__(self):
        self.cookies_file = Path("./cookies.txt")
        self.backup_dir = Path("./logs/cookies_backup")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Cookie有效期检查间隔 (小时)
        self.validity_check_interval = 24
        self.last_check_time = None
    
    def is_cookies_valid(self) -> bool:
        """检查cookies文件是否存在且有效"""
        try:
            if not self.cookies_file.exists():
                logger.info("Cookies文件不存在")
                return False
            
            # 检查文件大小
            if self.cookies_file.stat().st_size == 0:
                logger.warning("Cookies文件为空")
                return False
            
            # 检查文件内容
            with open(self.cookies_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()
                if not content or content == "# Netscape HTTP Cookie File":
                    logger.warning("Cookies文件内容无效")
                    return False
            
            # 检查关键cookies是否存在
            critical_cookies = self.get_critical_cookies()
            if not critical_cookies:
                logger.warning("未找到关键cookies")
                return False
            
            logger.info("Cookies文件验证通过")
            return True
            
        except Exception as e:
            logger.error(f"验证cookies文件失败: {e}")
            return False
    
    def get_critical_cookies(self) -> Dict[str, str]:
        """获取关键cookies"""
        try:
            cookies = self.parse_cookies_file()
            
            # 抖音关键cookies
            critical_keys = [
                'sessionid', 'sessionid_ss', 's_v_web_id', 'ttwid',
                'odin_tt', 'passport_csrf_token'
            ]
            
            critical_cookies = {}
            for key in critical_keys:
                if key in cookies:
                    critical_cookies[key] = cookies[key]
            
            return critical_cookies
            
        except Exception as e:
            logger.error(f"获取关键cookies失败: {e}")
            return {}
    
    def parse_cookies_file(self) -> Dict[str, str]:
        """解析cookies文件"""
        cookies = {}
        
        try:
            if not self.cookies_file.exists():
                return cookies
            
            with open(self.cookies_file, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    
                    # Netscape格式: domain, tailmatch, path, secure, expires, name, value
                    parts = line.split('\t')
                    if len(parts) >= 7:
                        name = parts[5]
                        value = parts[6]
                        cookies[name] = value
            
            return cookies
            
        except Exception as e:
            logger.error(f"解析cookies文件失败: {e}")
            return {}
    
    def backup_cookies(self) -> bool:
        """备份当前cookies"""
        try:
            if not self.cookies_file.exists():
                return False
            
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_file = self.backup_dir / f"cookies_backup_{timestamp}.txt"
            
            import shutil
            shutil.copy2(self.cookies_file, backup_file)
            
            logger.info(f"Cookies已备份到: {backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"备份cookies失败: {e}")
            return False
    
    def restore_cookies(self, backup_file: str) -> bool:
        """从备份恢复cookies"""
        try:
            backup_path = Path(backup_file)
            if not backup_path.exists():
                logger.error(f"备份文件不存在: {backup_file}")
                return False
            
            # 先备份当前文件
            if self.cookies_file.exists():
                self.backup_cookies()
            
            import shutil
            shutil.copy2(backup_path, self.cookies_file)
            
            logger.info(f"Cookies已从备份恢复: {backup_file}")
            return True
            
        except Exception as e:
            logger.error(f"恢复cookies失败: {e}")
            return False
    
    def get_backup_list(self) -> List[Dict[str, Any]]:
        """获取备份文件列表"""
        try:
            backups = []
            
            for backup_file in self.backup_dir.glob("cookies_backup_*.txt"):
                stat = backup_file.stat()
                backups.append({
                    "filename": backup_file.name,
                    "path": str(backup_file),
                    "size": stat.st_size,
                    "created_time": datetime.fromtimestamp(stat.st_ctime),
                    "modified_time": datetime.fromtimestamp(stat.st_mtime)
                })
            
            # 按创建时间降序排序
            backups.sort(key=lambda x: x["created_time"], reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"获取备份列表失败: {e}")
            return []
    
    def cleanup_old_backups(self, keep_count: int = 10) -> int:
        """清理旧的备份文件"""
        try:
            backups = self.get_backup_list()
            
            if len(backups) <= keep_count:
                return 0
            
            cleaned_count = 0
            for backup in backups[keep_count:]:
                try:
                    Path(backup["path"]).unlink()
                    cleaned_count += 1
                except Exception as e:
                    logger.warning(f"删除备份文件失败 {backup['filename']}: {e}")
            
            logger.info(f"已清理{cleaned_count}个旧备份文件")
            return cleaned_count
            
        except Exception as e:
            logger.error(f"清理备份文件失败: {e}")
            return 0
    
    def validate_cookie_format(self, cookies_content: str) -> bool:
        """验证cookie内容格式"""
        try:
            lines = cookies_content.strip().split('\n')
            
            # 至少应该有一行有效内容
            valid_lines = 0
            for line in lines:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                # 检查Netscape格式
                parts = line.split('\t')
                if len(parts) >= 7:
                    valid_lines += 1
            
            return valid_lines > 0
            
        except Exception as e:
            logger.error(f"验证cookie格式失败: {e}")
            return False
    
    def update_cookies_from_dict(self, cookies_dict: Dict[str, str]) -> bool:
        """从字典更新cookies文件"""
        try:
            # 先备份当前cookies
            if self.cookies_file.exists():
                self.backup_cookies()
            
            # 生成Netscape格式的cookies内容
            lines = ['# Netscape HTTP Cookie File']
            
            for name, value in cookies_dict.items():
                # 格式: domain, tailmatch, path, secure, expires, name, value
                line = f".douyin.com\tTRUE\t/\tFALSE\t0\t{name}\t{value}"
                lines.append(line)
            
            # 写入文件
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            
            logger.info(f"已更新cookies文件，包含{len(cookies_dict)}个cookies")
            return True
            
        except Exception as e:
            logger.error(f"更新cookies文件失败: {e}")
            return False
    
    def get_cookie_info(self) -> Dict[str, Any]:
        """获取cookie信息统计"""
        try:
            info = {
                "exists": self.cookies_file.exists(),
                "valid": False,
                "size": 0,
                "cookie_count": 0,
                "critical_cookies": 0,
                "last_modified": None,
                "backup_count": len(self.get_backup_list())
            }
            
            if info["exists"]:
                stat = self.cookies_file.stat()
                info["size"] = stat.st_size
                info["last_modified"] = datetime.fromtimestamp(stat.st_mtime)
                
                cookies = self.parse_cookies_file()
                info["cookie_count"] = len(cookies)
                
                critical_cookies = self.get_critical_cookies()
                info["critical_cookies"] = len(critical_cookies)
                
                info["valid"] = self.is_cookies_valid()
            
            return info
            
        except Exception as e:
            logger.error(f"获取cookie信息失败: {e}")
            return {
                "exists": False,
                "valid": False,
                "size": 0,
                "cookie_count": 0,
                "critical_cookies": 0,
                "last_modified": None,
                "backup_count": 0
            }
    
    def should_check_validity(self) -> bool:
        """检查是否需要验证cookie有效性"""
        if self.last_check_time is None:
            return True
        
        time_diff = datetime.now() - self.last_check_time
        return time_diff.total_seconds() > (self.validity_check_interval * 3600)
    
    def mark_validity_checked(self):
        """标记已检查有效性"""
        self.last_check_time = datetime.now()
    
    async def auto_validate_and_refresh(self) -> bool:
        """自动验证并刷新cookies（如果需要）"""
        try:
            # 检查是否需要验证
            if not self.should_check_validity():
                return True
            
            # 验证当前cookies
            if self.is_cookies_valid():
                self.mark_validity_checked()
                return True
            
            logger.warning("当前cookies无效，建议重新登录")
            return False
            
        except Exception as e:
            logger.error(f"自动验证cookies失败: {e}")
            return False


# 全局cookie管理器实例
_cookie_manager: Optional[CookieManager] = None


def get_cookie_manager() -> CookieManager:
    """获取cookie管理器实例"""
    global _cookie_manager
    if _cookie_manager is None:
        _cookie_manager = CookieManager()
    return _cookie_manager


def validate_cookies() -> bool:
    """验证cookies是否有效"""
    manager = get_cookie_manager()
    return manager.is_cookies_valid()


def get_cookies_info() -> Dict[str, Any]:
    """获取cookies信息"""
    manager = get_cookie_manager()
    return manager.get_cookie_info()


def update_cookies(cookies_dict: Dict[str, str]) -> bool:
    """更新cookies"""
    manager = get_cookie_manager()
    return manager.update_cookies_from_dict(cookies_dict)