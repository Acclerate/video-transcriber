# Video Transcriber API 文档

## 1. API 概述

Video Transcriber 提供 RESTful API 和 WebSocket API 两种接口方式，支持短视频链接转录为文本。

### 1.1 基础信息
- **Base URL**: `http://localhost:8000`
- **API Version**: v1
- **Content-Type**: `application/json`
- **字符编码**: UTF-8

### 1.2 支持的平台
- 抖音 (douyin.com, iesdouyin.com)
- B站 (bilibili.com)
- 更多平台持续添加中...

## 2. 认证

目前版本暂不需要认证，后续版本可能会添加 API Key 认证。

## 3. RESTful API

### 3.1 单个视频转录

#### 请求
```http
POST /api/v1/transcribe
Content-Type: application/json

{
    "url": "https://v.douyin.com/ieFvvPLX/",
    "options": {
        "model": "small",
        "language": "auto",
        "with_timestamps": true,
        "output_format": "json"
    }
}
```

#### 参数说明
| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| url | string | ✅ | - | 视频分享链接 |
| options.model | string | ❌ | "small" | Whisper模型: tiny/base/small/medium/large |
| options.language | string | ❌ | "auto" | 语言代码: auto/zh/en/ja等 |
| options.with_timestamps | boolean | ❌ | false | 是否包含时间戳 |
| options.output_format | string | ❌ | "json" | 输出格式: json/txt/srt/vtt |

#### 响应
```json
{
    "code": 200,
    "message": "转录成功",
    "data": {
        "task_id": "task_20240829_123456",
        "video_info": {
            "video_id": "7123456789",
            "title": "示例视频标题",
            "platform": "douyin",
            "duration": 30.5,
            "thumbnail": "https://example.com/thumb.jpg"
        },
        "transcription": {
            "text": "这是转录的完整文本内容",
            "language": "zh",
            "confidence": 0.95,
            "processing_time": 12.3,
            "segments": [
                {
                    "start_time": 0.0,
                    "end_time": 5.2,
                    "text": "这是第一段文本",
                    "confidence": 0.98
                },
                {
                    "start_time": 5.2,
                    "end_time": 10.8,
                    "text": "这是第二段文本",
                    "confidence": 0.92
                }
            ]
        }
    }
}
```

### 3.2 批量视频转录

#### 请求
```http
POST /api/v1/batch-transcribe
Content-Type: application/json

{
    "urls": [
        "https://v.douyin.com/ieFvvPLX/",
        "https://www.bilibili.com/video/BV1234567890",
        "https://v.douyin.com/xxxxxxxx/"
    ],
    "options": {
        "model": "small",
        "language": "auto",
        "max_concurrent": 3
    }
}
```

#### 参数说明
| 参数 | 类型 | 必填 | 默认值 | 描述 |
|------|------|------|--------|------|
| urls | array | ✅ | - | 视频链接数组，最多20个 |
| options.max_concurrent | integer | ❌ | 3 | 并发处理数量 |

#### 响应
```json
{
    "code": 200,
    "message": "批量任务已创建",
    "data": {
        "batch_id": "batch_20240829_123456",
        "total_count": 3,
        "task_ids": [
            "task_20240829_123457",
            "task_20240829_123458",
            "task_20240829_123459"
        ]
    }
}
```

### 3.3 查询任务状态

#### 请求
```http
GET /api/v1/status/{task_id}
```

#### 响应
```json
{
    "code": 200,
    "message": "查询成功",
    "data": {
        "task_id": "task_20240829_123456",
        "status": "completed",
        "progress": 100,
        "created_at": "2024-08-29T12:34:56Z",
        "completed_at": "2024-08-29T12:35:08Z",
        "result": {
            "text": "转录结果文本",
            "confidence": 0.95
        }
    }
}
```

#### 状态说明
| 状态 | 描述 |
|------|------|
| pending | 等待处理 |
| downloading | 正在下载视频 |
| extracting | 正在提取音频 |
| transcribing | 正在进行语音识别 |
| completed | 处理完成 |
| failed | 处理失败 |

### 3.4 查询批量任务状态

#### 请求
```http
GET /api/v1/batch-status/{batch_id}
```

#### 响应
```json
{
    "code": 200,
    "message": "查询成功",
    "data": {
        "batch_id": "batch_20240829_123456",
        "total_count": 3,
        "completed_count": 2,
        "failed_count": 0,
        "pending_count": 1,
        "tasks": [
            {
                "task_id": "task_20240829_123457",
                "status": "completed",
                "url": "https://v.douyin.com/ieFvvPLX/"
            },
            {
                "task_id": "task_20240829_123458",
                "status": "completed",
                "url": "https://www.bilibili.com/video/BV1234567890"
            },
            {
                "task_id": "task_20240829_123459",
                "status": "transcribing",
                "url": "https://v.douyin.com/xxxxxxxx/"
            }
        ]
    }
}
```

### 3.5 获取支持的平台

#### 请求
```http
GET /api/v1/platforms
```

#### 响应
```json
{
    "code": 200,
    "message": "查询成功",
    "data": {
        "platforms": [
            {
                "name": "douyin",
                "display_name": "抖音",
                "domains": ["douyin.com", "iesdouyin.com"],
                "supported": true
            },
            {
                "name": "bilibili",
                "display_name": "哔哩哔哩",
                "domains": ["bilibili.com"],
                "supported": true
            }
        ]
    }
}
```

## 4. WebSocket API

### 4.1 实时转录

用于获取实时处理进度和结果。

#### 连接
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/transcribe');
```

#### 发送消息
```javascript
ws.send(JSON.stringify({
    "action": "transcribe",
    "data": {
        "url": "https://v.douyin.com/ieFvvPLX/",
        "options": {
            "model": "small",
            "language": "auto"
        }
    }
}));
```

#### 接收消息

**进度更新**
```json
{
    "type": "progress",
    "data": {
        "task_id": "task_20240829_123456",
        "status": "downloading",
        "progress": 25,
        "message": "正在下载视频..."
    }
}
```

**处理完成**
```json
{
    "type": "result",
    "data": {
        "task_id": "task_20240829_123456",
        "transcription": {
            "text": "转录结果文本",
            "confidence": 0.95,
            "language": "zh"
        }
    }
}
```

**错误消息**
```json
{
    "type": "error",
    "data": {
        "task_id": "task_20240829_123456",
        "error_code": "DOWNLOAD_FAILED",
        "message": "视频下载失败"
    }
}
```

## 5. 错误代码

### 5.1 HTTP 状态码
- `200`: 成功
- `400`: 请求参数错误
- `404`: 资源不存在
- `429`: 请求频率过高
- `500`: 服务器内部错误

### 5.2 业务错误代码
| 错误代码 | 描述 | 解决方案 |
|----------|------|----------|
| INVALID_URL | 无效的视频链接 | 检查链接格式是否正确 |
| UNSUPPORTED_PLATFORM | 不支持的平台 | 使用支持的平台链接 |
| VIDEO_NOT_FOUND | 视频不存在 | 确认视频是否已删除或设为私密 |
| DOWNLOAD_FAILED | 视频下载失败 | 检查网络连接或稍后重试 |
| AUDIO_EXTRACT_FAILED | 音频提取失败 | 视频格式可能有问题 |
| TRANSCRIPTION_FAILED | 转录失败 | 音频质量可能过低 |
| RATE_LIMIT_EXCEEDED | 请求频率过高 | 降低请求频率 |

## 6. 使用示例

### 6.1 Python 示例
```python
import requests
import json

# 单个视频转录
url = "http://localhost:8000/api/v1/transcribe"
payload = {
    "url": "https://v.douyin.com/ieFvvPLX/",
    "options": {
        "model": "small",
        "with_timestamps": True
    }
}

response = requests.post(url, json=payload)
result = response.json()
print(result["data"]["transcription"]["text"])
```

### 6.2 JavaScript 示例
```javascript
// 使用 Fetch API
async function transcribeVideo(videoUrl) {
    const response = await fetch('/api/v1/transcribe', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            url: videoUrl,
            options: {
                model: 'small',
                with_timestamps: true
            }
        })
    });
    
    const result = await response.json();
    return result.data.transcription.text;
}
```

### 6.3 cURL 示例
```bash
# 单个视频转录
curl -X POST "http://localhost:8000/api/v1/transcribe" \
     -H "Content-Type: application/json" \
     -d '{
         "url": "https://v.douyin.com/ieFvvPLX/",
         "options": {
             "model": "small",
             "with_timestamps": true
         }
     }'

# 查询任务状态
curl -X GET "http://localhost:8000/api/v1/status/task_20240829_123456"
```

## 7. 性能指标

### 7.1 处理速度
- **Whisper Tiny**: ~10x 实时速度
- **Whisper Small**: ~5x 实时速度
- **Whisper Medium**: ~3x 实时速度
- **Whisper Large**: ~1.5x 实时速度

### 7.2 准确率
- **中文**: 95%+ (Small模型)
- **英文**: 97%+ (Small模型)
- **中英混合**: 92%+ (Small模型)

### 7.3 支持的音频格式
- MP3, WAV, MP4, M4A, FLAC, OGG
- 采样率: 16kHz (自动转换)
- 声道: 单声道/立体声 (自动处理)