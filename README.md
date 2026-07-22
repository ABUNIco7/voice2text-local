# voice2text-local

本地音频 / 视频转文字工具，基于 **faster-whisper**，运行在浏览器端，**无需上传文件到服务器**，隐私安全。

## 功能

- 拖拽或点击上传音频 / 视频文件（MP3、WAV、MP4、MOV、M4A 等）
- 浏览器端显示上传进度
- 本地自动转录（faster-whisper base 模型，中文）
- 支持下载：纯文字 (.txt) / SRT 字幕文件 (.srt)
- 复制文字到剪贴板
- 服务状态实时检测

## 快速开始

### 1. 安装依赖

```bash
pip install faster-whisper
```

### 2. 启动本地服务

```bash
python transcribe_server.py
```

服务启动后访问：**http://localhost:8765**

或在浏览器直接打开同目录下的 `voice2text.html` 文件。

### 3. 上传文件并转换

上传后点击「开始转换」，等待转录结果，支持复制或下载。

## 技术栈

| 组件 | 技术 |
|------|------|
| 前端 | HTML5 + JavaScript（原生，无框架） |
| 后端 | Python HTTP 服务器（内置） |
| 语音识别 | [faster-whisper](https://github.com/guillaumekln/faster-whisper) base 模型 |
| 运行环境 | Python 3.11+，Windows / macOS / Linux |

## 文件说明

- `voice2text.html` — 前端页面（浏览器打开即用）
- `transcribe_server.py` — 本地转录服务器（需 Python + faster-whisper）

## 隐私说明

所有文件仅在本地处理，**不会上传到任何远程服务器**。faster-whisper 模型在首次运行后自动缓存到本地。

## License

MIT
