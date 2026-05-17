# 字幕时间戳对齐逻辑

本文档记录当前 CLI/API 生成 SRT/VTT 字幕时的时间戳对齐链路。

## 总体策略

当前字幕对齐采用 **VAD-boundary-first** 策略：

```text
SenseVoice 识别文本
  ↓
SenseVoice VAD 提供人声段边界
  ↓
FA fa-zh 尝试生成逐字精确时间戳
  ↓
VAD 边界决定字幕出现/消失
  ↓
中文标点只负责拆分过长 VAD 段
  ↓
最终修正重叠和过短字幕
```

核心原则：

- 字幕的出现时间优先使用 SenseVoice VAD 检测到的人声开始时间。
- 字幕的消失时间优先使用 SenseVoice VAD 检测到的人声结束时间。
- FA 强制对齐只用于生成段内逐字时间戳，不作为整段字幕边界的主来源。
- 中文标点只用于拆分过长字幕，不用于决定人声段的整体起止。
- 当前优化目标以纯中文字幕为主，不再重点保护英文单词边界。

## 1. 主语音识别模型

主识别模型是 SenseVoice Small。

代码位置：

- `config/settings.py`：默认模型为 `sensevoice-small`
- `core/sensevoice_transcriber.py`：`MODEL_CONFIGS` 将 `sensevoice-small` 映射到 `iic/SenseVoiceSmall`
- `core/sensevoice_transcriber.py`：通过 FunASR `AutoModel` 加载模型

模型配置：

```text
模型名: sensevoice-small
ModelScope 仓库: iic/SenseVoiceSmall
用途: 主语音识别、多语言识别、中文优化
```

## 2. SenseVoice VAD 人声边界

SenseVoice 推理时启用 VAD 合并：

```python
merge_vad = True
merge_length_s = 5
```

在 `sentence` 或 `char` 时间戳模式下，还会启用：

```python
output_timestamp = True
```

代码位置：

- `core/sensevoice_transcriber.py`：`_build_rec_config()`

作用：

- SenseVoice 返回的每个 result entry 基本代表一个 VAD/merged speech 人声段。
- 每个人声段的首尾 timestamp 被保存为字幕的主起止边界。
- 后续即使 FA 替换了逐字时间戳，也不会丢弃这些 VAD 分段边界。

## 3. FA 强制对齐

FA 使用 FunASR 的中文强制对齐模型：

```text
模型: fa-zh
```

代码位置：

- `utils/forced_aligner.py`：`_FA_MODEL_ID = "fa-zh"`
- `core/sensevoice_transcriber.py`：`_align_with_fa()`

作用：

- 输入音频和 SenseVoice 已识别文本。
- 输出更精确的逐字时间戳。
- 如果 FA 成功，字幕内部逐字时间使用 FA 结果。
- 如果 FA 失败，回退到 SenseVoice 原始 timestamp。

FA 时间会叠加两个偏移：

```python
time_offset + FA_TIME_OFFSET
```

含义：

- `time_offset`：分块音频转回完整音频时间线时使用。
- `FA_TIME_OFFSET`：人工微调字幕同步的环境变量。

## 4. VAD-first 字幕分段

代码位置：

- `core/sensevoice_transcriber.py`：`_build_segments_vad_first()`

输入：

- `vad_segments`：SenseVoice VAD 人声段
- `char_timestamps`：FA 或 SenseVoice 的逐字时间戳
- `punctuated_text`：恢复标点后的文本
- `raw_text`：去特殊标记后的原始文本

逻辑：

1. 遍历每个 VAD 人声段。
2. 如果该段文本长度 `<= 25` 字：
   - 直接生成一条字幕。
   - `start_time` 使用 VAD 段开始时间。
   - `end_time` 使用 VAD 段结束时间。
3. 如果该段文本长度 `> 25` 字：
   - 在中文标点或自然中文边界处拆成多条字幕。
   - 子字幕内部时间使用逐字时间戳计算。
   - 最后一条子字幕的结束时间仍贴合 VAD 段结束时间。

这个阶段是当前对齐逻辑的核心：**VAD 决定整段字幕边界，逐字时间戳只参与长段内部拆分。**

## 5. 中文长句内部切分

相关代码位置：

- `core/sensevoice_transcriber.py`：`_build_raw_char_time_map()`
- `core/sensevoice_transcriber.py`：`_build_punct_to_raw_map()`
- `core/sensevoice_transcriber.py`：`_split_vad_segment_at_punctuation()`
- `core/sensevoice_transcriber.py`：`_find_chinese_natural_breaks()`

切分优先级：

1. 中文句末标点：

```text
。！？
```

2. 中文短停顿标点：

```text
，；：、
```

3. 如果没有合适标点，尝试中文自然边界：

```text
的 了 呢 吧 啊 吗 着 过 地 得
```

4. 如果仍然没有边界，则按长度强制切分。

映射逻辑：

- `raw_text` 通常不含标点。
- `punctuated_text` 含恢复后的中文标点。
- `_build_punct_to_raw_map()` 用于把标点文本位置映射回原始文本字符位置。
- 中文标点只标记断句位置，不消耗原文字符。

## 6. 分块音频合并

长音频会先被切块处理。

代码位置：

- `utils/audio/chunking.py`：`split_audio()`
- `utils/audio/chunking.py`：`merge_results()`
- `core/sensevoice_transcriber.py`：`_postprocess_chunked_result()`

分块策略：

- 每块有固定时长。
- 块之间保留 overlap，默认 2 秒。
- 每个 chunk 单独识别和对齐。

合并策略：

- chunk 内时间戳会加上该 chunk 的全局 `start_time`。
- 合并逐字时间戳时，跳过和上一块重叠的重复时间戳。
- 合并 VAD 分段时，跳过和已合并 VAD 段重叠的分段。
- 合并完成后，仍然使用 VAD-first 逻辑重新生成最终字幕 segments。

## 7. 最终时间修正

代码位置：

- `utils/subtitle_timing.py`：`fix_subtitle_segment_timing()`
- `core/sensevoice_transcriber.py`：`_dedupe_and_fix_segment_timing()`

作用：

- 移除空字幕。
- 合并过短字幕。
- 修复相邻字幕重叠。

VAD-first 路径使用：

```python
subtitle_hold_seconds = 0.0
```

原因：

- 当前目标是“人声结束，字幕结束”。
- 如果额外延长字幕显示时间，会破坏 VAD 人声结束边界。

## 8. 回退逻辑

当前存在以下回退路径：

1. FA 失败：
   - 回退到 SenseVoice 原始时间戳。

2. 没有 VAD 分段：
   - 回退到旧的标点断句 + 字符时间戳对齐逻辑。

3. 长句没有标点：
   - 尝试中文自然边界。
   - 仍失败则按长度强制切分。

## 9. 当前对齐逻辑的优先级

从高到低：

1. SenseVoice VAD 人声起止边界
2. FA `fa-zh` 逐字强制对齐时间戳
3. SenseVoice 原始逐字 timestamp fallback
4. 中文标点切分
5. 中文自然边界切分
6. 最终重叠/过短字幕修正

简化理解：

```text
VAD 管整段开始结束
FA 管段内每个字
标点只管太长时怎么拆
最终修正只处理异常边界
```
