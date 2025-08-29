"""
日志配置模块
统一的日志管理和配置
"""

import sys
import os
from pathlib import Path
from typing import Optional
from loguru import logger


class LoggerConfig:
    """日志配置类"""
    
    def __init__(
        self,
        log_level: str = "INFO",
        log_file: Optional[str] = None,
        log_to_console: bool = True,
        log_max_size: str = "10 MB",
        log_backup_count: int = 5,
        log_format: Optional[str] = None
    ):
        """
        初始化日志配置
        
        Args:
            log_level: 日志级别
            log_file: 日志文件路径
            log_to_console: 是否输出到控制台
            log_max_size: 日志文件最大大小
            log_backup_count: 保留的日志文件数量
            log_format: 日志格式
        """
        self.log_level = log_level.upper()
        self.log_file = log_file
        self.log_to_console = log_to_console
        self.log_max_size = log_max_size
        self.log_backup_count = log_backup_count
        
        # 默认日志格式
        if log_format is None:
            self.log_format = (
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            )
        else:
            self.log_format = log_format
        
        self.setup_logger()
    
    def setup_logger(self):
        """设置日志器"""
        # 清除默认处理器
        logger.remove()
        
        # 控制台输出
        if self.log_to_console:
            logger.add(
                sys.stdout,
                format=self.log_format,
                level=self.log_level,
                colorize=True,
                backtrace=True,
                diagnose=True
            )
        
        # 文件输出
        if self.log_file:
            # 确保日志目录存在
            log_path = Path(self.log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            logger.add(
                self.log_file,
                format=self.log_format,
                level=self.log_level,
                rotation=self.log_max_size,
                retention=self.log_backup_count,
                compression="zip",
                backtrace=True,
                diagnose=True,
                encoding="utf-8"
            )
    
    def set_level(self, level: str):
        """动态设置日志级别"""
        self.log_level = level.upper()
        self.setup_logger()
    
    def add_file_handler(self, file_path: str, level: Optional[str] = None):
        """添加文件处理器"""
        log_path = Path(file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        logger.add(
            file_path,
            format=self.log_format,
            level=level or self.log_level,
            rotation=self.log_max_size,
            retention=self.log_backup_count,
            compression="zip",
            backtrace=True,
            diagnose=True,
            encoding="utf-8"
        )


def setup_default_logger(
    log_level: str = "INFO",
    log_file: Optional[str] = "./logs/app.log",
    log_to_console: bool = True
) -> LoggerConfig:
    """
    设置默认日志配置
    
    Args:
        log_level: 日志级别
        log_file: 日志文件路径
        log_to_console: 是否输出到控制台
        
    Returns:
        LoggerConfig: 日志配置实例
    """
    return LoggerConfig(
        log_level=log_level,
        log_file=log_file,
        log_to_console=log_to_console
    )


def get_logger(name: str = None):
    """
    获取日志器实例
    
    Args:
        name: 日志器名称
        
    Returns:
        logger: 日志器实例
    """
    if name:
        return logger.bind(name=name)
    return logger


# 模块级别的日志器配置
_logger_config = None


def init_logger_from_env():
    """从环境变量初始化日志器"""
    global _logger_config
    
    log_level = os.getenv("LOG_LEVEL", "INFO")
    log_file = os.getenv("LOG_FILE", "./logs/app.log")
    log_to_console = os.getenv("LOG_TO_CONSOLE", "true").lower() == "true"
    log_max_size = os.getenv("LOG_MAX_SIZE", "10 MB")
    log_backup_count = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    _logger_config = LoggerConfig(
        log_level=log_level,
        log_file=log_file,
        log_to_console=log_to_console,
        log_max_size=log_max_size,
        log_backup_count=log_backup_count
    )
    
    return _logger_config


def get_logger_config() -> Optional[LoggerConfig]:
    """获取当前日志配置"""
    return _logger_config


# 便捷的日志记录函数
def log_debug(message: str, **kwargs):
    """记录调试信息"""
    logger.debug(message, **kwargs)


def log_info(message: str, **kwargs):
    """记录一般信息"""
    logger.info(message, **kwargs)


def log_warning(message: str, **kwargs):
    """记录警告信息"""
    logger.warning(message, **kwargs)


def log_error(message: str, **kwargs):
    """记录错误信息"""
    logger.error(message, **kwargs)


def log_critical(message: str, **kwargs):
    """记录严重错误信息"""
    logger.critical(message, **kwargs)


def log_exception(message: str, **kwargs):
    """记录异常信息"""
    logger.exception(message, **kwargs)


# 装饰器：记录函数执行
def log_execution(func_name: Optional[str] = None, log_level: str = "INFO"):
    """
    装饰器：记录函数执行
    
    Args:
        func_name: 函数名称
        log_level: 日志级别
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            name = func_name or func.__name__
            start_time = logger._core.time()
            
            logger.log(log_level, f"开始执行: {name}")
            try:
                result = await func(*args, **kwargs)
                end_time = logger._core.time()
                duration = end_time - start_time
                logger.log(log_level, f"执行完成: {name}, 耗时: {duration:.3f}秒")
                return result
            except Exception as e:
                end_time = logger._core.time()
                duration = end_time - start_time
                logger.error(f"执行失败: {name}, 耗时: {duration:.3f}秒, 错误: {e}")
                raise
        
        def sync_wrapper(*args, **kwargs):
            name = func_name or func.__name__
            start_time = logger._core.time()
            
            logger.log(log_level, f"开始执行: {name}")
            try:
                result = func(*args, **kwargs)
                end_time = logger._core.time()
                duration = end_time - start_time
                logger.log(log_level, f"执行完成: {name}, 耗时: {duration:.3f}秒")
                return result
            except Exception as e:
                end_time = logger._core.time()
                duration = end_time - start_time
                logger.error(f"执行失败: {name}, 耗时: {duration:.3f}秒, 错误: {e}")
                raise
        
        # 判断是否为异步函数
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator


# 上下文管理器：临时改变日志级别
class TemporaryLogLevel:
    """临时改变日志级别的上下文管理器"""
    
    def __init__(self, level: str):
        self.new_level = level.upper()
        self.old_handlers = []
    
    def __enter__(self):
        # 保存当前处理器
        self.old_handlers = logger._core.handlers.copy()
        
        # 移除所有处理器
        logger.remove()
        
        # 添加临时处理器
        logger.add(
            sys.stdout,
            level=self.new_level,
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>"
        )
        
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        # 移除临时处理器
        logger.remove()
        
        # 恢复原有处理器
        for handler_id, handler in self.old_handlers.items():
            logger._core.handlers[handler_id] = handler


if __name__ == "__main__":
    # 测试日志配置
    
    # 基本测试
    config = setup_default_logger(log_level="DEBUG")
    
    logger.debug("这是调试信息")
    logger.info("这是一般信息")
    logger.warning("这是警告信息")
    logger.error("这是错误信息")
    
    # 测试装饰器
    @log_execution("测试函数")
    def test_function():
        import time
        time.sleep(0.1)
        return "测试结果"
    
    result = test_function()
    logger.info(f"函数返回: {result}")
    
    # 测试临时日志级别
    with TemporaryLogLevel("ERROR"):
        logger.debug("这条调试信息不会显示")
        logger.info("这条信息也不会显示")
        logger.error("只有这条错误信息会显示")
    
    logger.info("恢复正常日志级别")