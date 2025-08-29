# 抖音扫码登录使用指南

## 概述

抖音扫码登录功能允许用户通过扫描二维码自动获取抖音cookies，解决视频解析过程中的反爬虫限制问题。这个功能通过浏览器自动化技术，提供便捷的一键登录体验。

## 功能特点

- 🔒 **安全可靠**: 使用官方登录流程，保护用户隐私
- ⚡ **快速便捷**: 一键启动，扫码即可完成登录
- 🔄 **自动更新**: 自动保存最新cookies到本地文件
- 📱 **实时状态**: WebSocket实时显示登录进度
- 🛡️ **错误恢复**: 智能重试机制，提高成功率

## 使用步骤

### 1. 启动扫码登录

在Web界面的"单个转录"页面顶部，找到"抖音扫码登录"卡片：

![扫码登录界面](images/qr_login_interface.png)

点击"**开始扫码登录**"按钮启动登录流程。

### 2. 扫描二维码

系统会自动：
- 启动浏览器并访问抖音登录页面
- 生成并显示二维码
- 显示实时状态更新

![二维码显示](images/qr_code_display.png)

使用手机上的**抖音APP**扫描显示的二维码。

### 3. 确认登录

在手机上：
- 打开抖音APP
- 扫描二维码
- 在APP中确认登录授权

页面会实时显示登录状态：
- "等待扫码..." → "扫描成功，请在手机上确认登录" → "登录成功！"

### 4. 完成登录

登录成功后：
- 系统自动保存cookies到 `cookies.txt` 文件
- 状态显示更新为"已登录"
- 可以正常使用抖音视频转录功能

## 状态说明

| 状态 | 描述 |
|-----|------|
| 未登录 | 当前没有有效的cookies |
| 正在初始化浏览器... | 正在启动自动化浏览器 |
| 二维码已生成 | 二维码准备就绪，等待扫描 |
| 请使用抖音APP扫描二维码 | 显示二维码，等待用户扫描 |
| 扫描成功，请在手机上确认登录 | 二维码已扫描，等待手机确认 |
| 登录成功！Cookies已保存 | 登录完成，cookies已更新 |
| 已登录 | 当前有有效的cookies |

## 功能按钮

### 开始扫码登录
启动扫码登录流程，会自动打开浏览器并生成二维码。

### 停止登录
中止当前的登录流程，关闭浏览器并清理资源。

### 检查状态
检查当前cookies的有效性状态，更新显示状态。

## API接口

### WebSocket接口

连接地址：`ws://localhost:8000/ws/auth/douyin`

#### 消息格式

**状态变化通知：**
```json
{
  "type": "status_change",
  "status": "qr_generated",
  "message": "二维码已生成"
}
```

**登录结果：**
```json
{
  "type": "login_result",
  "status": "success",
  "message": "登录成功",
  "qr_code": "data:image/png;base64,iVBORw0KGgo...",
  "cookies_count": 6
}
```

**客户端控制：**
```json
{
  "action": "refresh_qr"  // 刷新二维码
}
```

```json
{
  "action": "stop"  // 停止登录
}
```

### HTTP接口

#### 启动登录
```http
POST /api/v1/auth/douyin/start
```

#### 查询状态
```http
GET /api/v1/auth/douyin/status
```

#### 停止登录
```http
POST /api/v1/auth/douyin/stop
```

## Cookie管理

### 文件位置
Cookies保存在项目根目录的 `cookies.txt` 文件中。

### 格式说明
使用标准的Netscape cookies格式：
```
# Netscape HTTP Cookie File
.douyin.com	TRUE	/	FALSE	0	sessionid	xxxxxx
.douyin.com	TRUE	/	FALSE	0	s_v_web_id	xxxxxx
```

### 自动备份
系统会自动备份cookies文件到 `logs/cookies_backup/` 目录，便于恢复。

### Cookie验证
系统会检查以下关键cookies是否存在：
- `sessionid` / `sessionid_ss`
- `s_v_web_id`
- `ttwid`
- `odin_tt`
- `passport_csrf_token`

## 常见问题

### Q: 二维码无法显示或一直加载？
A: 请检查：
- 网络连接是否正常
- 是否安装了Playwright浏览器：`playwright install`
- 防火墙是否阻止了浏览器启动

### Q: 扫码后显示"登录失败"？
A: 可能的原因：
- 二维码已过期（5分钟有效期）
- 网络连接中断
- 抖音安全策略变化

解决方法：点击"停止登录"后重新开始。

### Q: 登录成功但视频解析仍然失败？
A: 请检查：
- Cookies文件是否正确生成（`cookies.txt`）
- 尝试重启API服务使新cookies生效
- 检查cookies是否包含必要的字段

### Q: 如何知道cookies是否过期？
A: 可以通过以下方式检查：
- 点击"检查状态"按钮
- 观察视频解析是否成功
- 查看API返回的错误信息

### Q: 可以同时登录多个抖音账号吗？
A: 当前版本每次只能保存一个账号的cookies。如需切换账号，请重新进行扫码登录。

## 技术原理

### 浏览器自动化
使用Playwright框架控制Chromium浏览器：
- 访问抖音官方登录页面
- 自动点击扫码登录选项
- 截取二维码图片
- 监听登录状态变化

### 实时通信
通过WebSocket提供实时状态更新：
- 二维码生成通知
- 登录进度状态
- 错误信息反馈

### 安全保护
- 使用官方登录流程，不涉及账号密码
- 本地存储cookies，不上传到外部服务器
- 自动清理浏览器数据

### Cookie提取
- 过滤抖音相关域名的cookies
- 提取关键认证字段
- 转换为标准格式保存

## 依赖要求

### Python包
```
playwright>=1.40.0
Pillow>=10.1.0
```

### 系统要求
- 支持图形界面的操作系统
- 足够的内存运行浏览器（建议4GB以上）
- 稳定的网络连接

### 安装说明
```bash
# 安装Python依赖
pip install playwright Pillow

# 安装浏览器
playwright install

# 或者只安装Chromium
playwright install chromium
```

## 高级配置

### 浏览器选项
可以在 `core/douyin_auth.py` 中调整浏览器启动参数：

```python
self.browser = await self.playwright.chromium.launch(
    headless=True,  # 设置为False可以看到浏览器界面
    args=[
        '--no-sandbox',
        '--disable-blink-features=AutomationControlled',
        '--disable-dev-shm-usage',
    ]
)
```

### 超时设置
```python
self.timeout = 300  # 登录超时时间（秒）
self.check_interval = 2  # 状态检查间隔（秒）
```

### 自定义User-Agent
```python
user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
```

## 更新日志

### v1.0.0 (2024-01-XX)
- ✨ 新增抖音扫码登录功能
- 🔄 支持实时状态更新
- 🛡️ 增强错误处理和重试机制
- 📱 优化移动端扫码体验
- 💾 自动cookie管理和备份

## 反馈与支持

如果您在使用过程中遇到问题，请：

1. 查看控制台日志获取详细错误信息
2. 检查 `logs/api.log` 文件
3. 在项目GitHub页面提交Issue
4. 提供详细的错误描述和日志信息

---

**注意：** 此功能需要合规使用，请遵守抖音平台的使用条款和相关法律法规。