#!/usr/bin/env python3
"""
Video Transcriber API启动脚本
"""

import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置环境变量
os.environ.setdefault("PYTHONPATH", str(project_root))

if __name__ == "__main__":
    import uvicorn
    from api.main import app
    
    # 配置参数
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    reload = os.getenv("RELOAD", "true").lower() == "true"
    
    print(f"启动Video Transcriber API服务...")
    print(f"访问地址: http://{host}:{port}")
    print(f"API文档: http://{host}:{port}/docs")
    print(f"使用CUDA: {os.environ.get('CUDA_VISIBLE_DEVICES', '0')}")
    
    # 启动服务
    uvicorn.run(
        "api.main:app",
        host=host,
        port=port,
        reload=reload,
        access_log=True,
        log_level="info"
    )