"""
模型下载工具
支持 SenseVoice 模型下载
"""

import os
from pathlib import Path
from typing import Optional
from loguru import logger


# SenseVoice 模型配置
SENSEVOICE_MODELS = {
    "sensevoice-small": {
        "repo": "iic/SenseVoiceSmall",
        "name": "SenseVoice Small",
        "size": "244MB",
        "description": "多语言语音识别，中文优化"
    }
}


def download_sensevoice_model(
    model_name: str = "sensevoice-small",
    cache_dir: str = "./models_cache",
    progress_callback: Optional[callable] = None
) -> str:
    """
    从 ModelScope 下载 SenseVoice 模型

    Args:
        model_name: 模型名称
        cache_dir: 缓存目录
        progress_callback: 进度回调函数

    Returns:
        str: 模型目录路径
    """
    if model_name not in SENSEVOICE_MODELS:
        raise ValueError(f"不支持的 SenseVoice 模型: {model_name}")

    repo_id = SENSEVOICE_MODELS[model_name]["repo"]

    logger.info(f"从 ModelScope 下载 SenseVoice 模型: {repo_id}")

    try:
        from modelscope import snapshot_download

        # 使用 ModelScope 下载模型
        model_dir = snapshot_download(
            repo_id,
            cache_dir=cache_dir,
            revision="master"
        )

        logger.info(f"SenseVoice 模型下载完成: {model_dir}")

        return model_dir

    except ImportError:
        raise RuntimeError(
            "需要安装 modelscope 库。请运行: pip install modelscope"
        )
    except Exception as e:
        logger.error(f"SenseVoice 模型下载失败: {e}")
        raise


def download_model(
    model_name: str = "sensevoice-small",
    cache_dir: str = "./models_cache",
    source: str = "auto",
    progress_callback: Optional[callable] = None
) -> str:
    """
    下载语音识别模型

    Args:
        model_name: 模型名称 (sensevoice-small)
        cache_dir: 缓存目录
        source: 下载源 (仅支持 ModelScope)
        progress_callback: 进度回调函数

    Returns:
        str: 下载的模型文件路径
    """
    return download_sensevoice_model(model_name, cache_dir, progress_callback)


def list_available_models() -> dict:
    """列出可用的语音识别模型"""
    return {
        "sensevoice-small": {
            "size": "244MB",
            "description": "多语言语音识别，中文优化",
            "type": "SenseVoice"
        }
    }


if __name__ == "__main__":
    # 测试下载
    import sys

    model = sys.argv[1] if len(sys.argv) > 1 else "sensevoice-small"

    print(f"开始下载 SenseVoice {model} 模型...")
    print(f"支持: {', '.join(list_available_models().keys())}")

    try:
        filepath = download_model(model, source="auto")
        print(f"\n下载成功: {filepath}")
    except Exception as e:
        print(f"\n下载失败: {e}")
        sys.exit(1)
