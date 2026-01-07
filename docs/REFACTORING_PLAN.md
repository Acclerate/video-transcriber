# Video Transcriber 项目重构方案

## 一、当前问题分析

### 1.1 代码冗余
- FFmpeg 检测函数在多处重复
- 日志配置分散
- 工具函数混杂在一起

### 1.2 结构混乱
- 根目录有大量测试文件
- 配置分散在多个文件
- 职责不清晰

### 1.3 模块耦合
- API 直接导入全局实例
- 缺少服务层抽象

---

## 二、目标结构

```
video-transcriber/
├── api/                        # API 接口层
│   ├── __init__.py
│   ├── main.py                 # FastAPI 应用
│   ├── routes/                 # 路由模块
│   │   ├── __init__.py
│   │   ├── transcribe.py       # 转录相关路由
│   │   ├── health.py           # 健康检查
│   │   └── websocket.py        # WebSocket 路由
│   └── dependencies.py         # API 依赖注入
│
├── core/                       # 核心业务逻辑
│   ├── __init__.py
│   ├── engine.py               # 转录引擎
│   ├── transcriber.py          # Whisper 封装
│   └── downloader.py           # 音频提取
│
├── services/                   # 服务层 (新增)
│   ├── __init__.py
│   ├── transcription_service.py    # 转录服务
│   ├── file_service.py             # 文件服务
│   └── task_service.py             # 任务管理服务
│
├── config/                     # 配置管理 (新增)
│   ├── __init__.py
│   ├── settings.py             # 应用配置
│   └── constants.py            # 常量定义
│
├── utils/                      # 工具函数 (重组)
│   ├── __init__.py
│   ├── ffmpeg/                 # FFmpeg 相关 (新增)
│   │   ├── __init__.py
│   │   ├── checker.py          # FFmpeg 检测
│   │   └── helpers.py          # FFmpeg 辅助函数
│   ├── logging/                # 日志管理 (重组)
│   │   ├── __init__.py
│   │   └── config.py           # 日志配置
│   ├── file/                   # 文件工具 (新增)
│   │   ├── __init__.py
│   │   └── helpers.py          # 文件操作
│   ├── audio/                  # 音频工具 (新增)
│   │   ├── __init__.py
│   │   └── helpers.py          # 音频处理
│   └── common/                 # 通用工具
│       ├── __init__.py
│       └── helpers.py          # 通用辅助函数
│
├── models/                     # 数据模型
│   ├── __init__.py
│   ├── schemas.py              # Pydantic 模型
│   ├── enums.py                # 枚举类型 (新增)
│   └── entities.py             # 实体定义 (新增)
│
├── tests/                      # 测试文件 (整理)
│   ├── __init__.py
│   ├── conftest.py             # pytest 配置
│   ├── unit/                   # 单元测试
│   │   ├── __init__.py
│   │   ├── test_engine.py
│   │   ├── test_transcriber.py
│   │   ├── test_downloader.py
│   │   ├── test_services.py
│   │   └── test_utils.py
│   ├── integration/            # 集成测试
│   │   ├── __init__.py
│   │   ├── test_api.py
│   │   └── test_workflow.py
│   └── e2e/                    # 端到端测试
│       ├── __init__.py
│       └── test_full_transcription.py
│
├── scripts/                    # 脚本工具 (新增)
│   ├── __init__.py
│   ├── check_deps.py           # 依赖检查
│   └── cleanup.py              # 清理工具
│
├── docker/                     # Docker 配置
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── docs/                       # 文档
│   ├── architecture.md         # 架构文档
│   ├── api.md                  # API 文档
│   └── deployment.md           # 部署文档
│
├── web/                        # 前端资源
│   ├── index.html
│   ├── style.css
│   └── script.js
│
├── logs/                       # 日志目录
├── temp/                       # 临时文件
├── output/                     # 输出文件
│
├── main.py                     # CLI 入口
├── start_api.py                # API 启动器
├── requirements.txt            # 依赖清单
├── .env.example                # 环境变量模板
├── .gitignore
├── pytest.ini
└── README.md
```

---

## 三、重构步骤

### 第一阶段：创建新结构 (高优先级)

#### 1.1 创建配置模块
```
config/
├── __init__.py
├── settings.py         # 使用 pydantic-settings
└── constants.py        # 常量定义
```

**职责**:
- 集中管理所有配置
- 环境变量验证
- 不同环境配置 (dev/test/prod)

#### 1.2 创建服务层
```
services/
├── __init__.py
├── transcription_service.py   # 转录业务逻辑
├── file_service.py            # 文件操作
└── task_service.py            # 任务管理
```

**职责**:
- 封装核心业务逻辑
- 协调多个 core 模块
- 为 API 和 CLI 提供统一接口

#### 1.3 重组工具模块
```
utils/
├── ffmpeg/            # FFmpeg 相关
│   ├── checker.py     # 检测功能
│   └── helpers.py     # 辅助函数
├── logging/           # 日志配置
│   └── config.py
├── file/              # 文件工具
│   └── helpers.py
├── audio/             # 音频工具
│   └── helpers.py
└── common/            # 通用工具
    └── helpers.py
```

### 第二阶段：整理测试 (中优先级)

#### 2.1 移动测试文件
```
tests/
├── unit/              # 从 core/ 移动单元测试
├── integration/       # API 集成测试
└── e2e/              # 端到端测试
```

#### 2.2 删除根目录测试文件
```
需要删除/移动的文件:
- test_api.py (根目录)
- test_ffmpeg_check.py -> tests/unit/test_ffmpeg.py
- test_user_video_real.py -> tests/integration/
- test_douyin_simulation.py -> tests/integration/
- debug_user_video.py -> scripts/
- test_with_cookies.py -> tests/integration/
- test_douyin_login_complete.py -> tests/integration/
- test_qr_login_real.py -> tests/integration/
```

### 第三阶段：重构 API (中优先级)

#### 3.1 拆分路由
```
api/routes/
├── __init__.py
├── transcribe.py      # /api/v1/transcribe
├── health.py          # /health
└── websocket.py       # /ws
```

#### 3.2 使用服务层
```python
# 之前: API 直接调用 core
from core import transcription_engine

# 之后: API 调用服务层
from services import TranscriptionService
```

### 第四阶段：更新导入 (低优先级)

#### 4.1 更新所有导入路径
```python
# 之前
from utils import check_ffmpeg_installed

# 之后
from utils.ffmpeg.checker import check_ffmpeg_installed
```

#### 4.2 更新 __init__.py
确保每个模块都有清晰的导出

---

## 四、详细模块设计

### 4.1 配置模块 (config/)

```python
# config/settings.py
from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    """应用配置"""
    # 服务配置
    HOST: str = "0.0.0.0"
    PORT: int = 8665
    DEBUG: bool = False

    # Whisper 配置
    DEFAULT_MODEL: str = "small"
    ENABLE_GPU: bool = True

    # 文件配置
    TEMP_DIR: str = "./temp"
    OUTPUT_DIR: str = "./output"
    MAX_FILE_SIZE: int = 500  # MB

    # 日志配置
    LOG_LEVEL: str = "INFO"
    LOG_FILE: str = "./logs/app.log"

    class Config:
        env_file = ".env"

settings = Settings()
```

### 4.2 服务层 (services/)

```python
# services/transcription_service.py
class TranscriptionService:
    """转录服务"""

    def __init__(self, config: Settings):
        self.config = config
        self.engine = VideoTranscriptionEngine()

    async def transcribe(
        self,
        file_path: str,
        options: ProcessOptions
    ) -> TranscriptionResult:
        """执行转录"""
        # 业务逻辑
        pass

    async def transcribe_batch(
        self,
        file_paths: List[str],
        options: ProcessOptions
    ) -> BatchResult:
        """批量转录"""
        pass
```

### 4.3 工具模块重组

```python
# utils/ffmpeg/checker.py
def check_ffmpeg_installed() -> bool:
    """检查 FFmpeg 是否安装"""
    pass

def get_ffmpeg_version() -> Optional[str]:
    """获取 FFmpeg 版本"""
    pass

# utils/file/helpers.py
def validate_video_file(file_path: str) -> bool:
    """验证视频文件"""
    pass

def get_video_info(file_path: str) -> VideoInfo:
    """获取视频信息"""
    pass
```

---

## 五、依赖关系图

```
┌─────────────────────────────────────────────────────────────┐
│                        入口层                                 │
│  ┌──────────────┐         ┌──────────────┐                 │
│  │   main.py    │         │  api/main.py │                 │
│  │     CLI      │         │    FastAPI   │                 │
│  └──────────────┘         └──────────────┘                 │
└─────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────────────────────────────────────────────────┐
│                        服务层                                 │
│  ┌──────────────────┐  ┌──────────────────┐               │
│  │TranscriptionSvc  │  │   FileService    │               │
│  └──────────────────┘  └──────────────────┘               │
└─────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────────────────────────────────────────────────┐
│                        核心层                                 │
│  ┌──────────┐  ┌─────────────┐  ┌──────────────┐          │
│  │ Engine   │  │Transcriber  │  │ Downloader   │          │
│  └──────────┘  └─────────────┘  └──────────────┘          │
└─────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────────────────────────────────────────────────┐
│                        工具层                                 │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │  ffmpeg  │  │  audio   │  │   file   │  │  logging │  │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │
└─────────────────────────────────────────────────────────────┘
         │                          │
         ▼                          ▼
┌─────────────────────────────────────────────────────────────┐
│                        配置层                                 │
│           ┌──────────────────────────────┐                  │
│           │        config/settings       │                  │
│           └──────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
```

---

## 六、迁移清单

### 6.1 需要创建的文件

#### 配置模块
- [ ] `config/__init__.py`
- [ ] `config/settings.py`
- [ ] `config/constants.py`

#### 服务层
- [ ] `services/__init__.py`
- [ ] `services/transcription_service.py`
- [ ] `services/file_service.py`
- [ ] `services/task_service.py`

#### 重组工具
- [ ] `utils/ffmpeg/__init__.py`
- [ ] `utils/ffmpeg/checker.py`
- [ ] `utils/ffmpeg/helpers.py`
- [ ] `utils/logging/__init__.py`
- [ ] `utils/logging/config.py`
- [ ] `utils/file/__init__.py`
- [ ] `utils/file/helpers.py`
- [ ] `utils/audio/__init__.py`
- [ ] `utils/audio/helpers.py`
- [ ] `utils/common/__init__.py`
- [ ] `utils/common/helpers.py`

#### API 路由
- [ ] `api/routes/__init__.py`
- [ ] `api/routes/transcribe.py`
- [ ] `api/routes/health.py`
- [ ] `api/routes/websocket.py`

#### 测试
- [ ] `tests/unit/__init__.py`
- [ ] `tests/unit/test_engine.py`
- [ ] `tests/unit/test_transcriber.py`
- [ ] `tests/unit/test_downloader.py`
- [ ] `tests/unit/test_ffmpeg.py`
- [ ] `tests/integration/__init__.py`
- [ ] `tests/e2e/__init__.py`

#### 脚本
- [ ] `scripts/__init__.py`
- [ ] `scripts/check_deps.py`
- [ ] `scripts/cleanup.py`

### 6.2 需要移动的文件

#### 测试文件移动
- `test_ffmpeg_check.py` → `tests/unit/test_ffmpeg.py`
- `test_user_video_real.py` → `tests/integration/`
- `test_douyin_simulation.py` → `tests/integration/`
- `test_with_cookies.py` → `tests/integration/`
- `test_douyin_login_complete.py` → `tests/integration/`
- `test_qr_login_real.py` → `tests/integration/`

#### 脚本移动
- `verify_ffmpeg.py` → `scripts/check_deps.py`
- `debug_user_video.py` → `scripts/`

### 6.3 需要删除的文件

- [ ] `test_api.py` (根目录，与 tests/test_api.py 重复)
- [ ] `simple_api_test.py` (测试代码，应整合)
- [ ] `run_tests.py` (使用 pytest 直接运行)
- [ ] `test_report.md`, `FINAL_TEST_REPORT.md`, `test_douyin_login_report.md` (移到 docs/)

### 6.4 需要修改的文件

- [ ] `main.py` - 使用新的服务层
- [ ] `api/main.py` - 使用新的服务层和路由
- [ ] `api/__init__.py` - 更新导出
- [ ] `utils/__init__.py` - 重组导出
- [ ] `core/__init__.py` - 保持不变
- [ ] `models/__init__.py` - 可能需要拆分
- [ ] `requirements.txt` - 添加 pydantic-settings

---

## 七、执行顺序

```
第1步: 创建新目录结构
    ├─ 创建 config/
    ├─ 创建 services/
    ├─ 重组 utils/
    └─ 创建 api/routes/

第2步: 创建新模块
    ├─ 配置模块 (config/settings.py)
    ├─ 服务层基础框架
    └─ 重组工具函数

第3步: 移动和清理测试
    ├─ 移动测试文件到 tests/
    ├─ 删除根目录测试文件
    └─ 创建缺失的单元测试

第4步: 重构 API
    ├─ 拆分路由到 api/routes/
    ├─ 使用服务层
    └─ 更新依赖注入

第5步: 更新 CLI
    ├─ 使用服务层
    ├─ 使用配置模块
    └─ 清理导入

第6步: 更新文档
    ├─ README.md
    ├─ 架构文档
    └─ API 文档

第7步: 验证和测试
    ├─ 运行所有测试
    ├─ 检查导入
    └─ 确保功能正常
```

---

## 八、预期收益

### 8.1 代码质量
- ✅ 消除代码重复
- ✅ 清晰的职责划分
- ✅ 更好的可测试性

### 8.2 可维护性
- ✅ 模块化设计
- ✅ 低耦合高内聚
- ✅ 统一的配置管理

### 8.3 可扩展性
- ✅ 服务层抽象
- ✅ 依赖注入准备
- ✅ 清晰的扩展点

---

## 九、风险和注意事项

1. **向后兼容性**: 重构后确保 CLI 和 API 接口不变
2. **测试覆盖**: 重构过程中保持测试通过
3. **渐进式重构**: 分阶段进行，每阶段可独立验证
4. **文档更新**: 同步更新文档和注释

---

*文档版本: 1.0*
*创建日期: 2025-01-07*
*最后更新: 2025-01-07*
