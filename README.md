# SmartSisi AI Assistant 🤖

SmartSisi 是一个智能语音助手系统，集成了多种 AI 能力，包括语音识别、自然语言处理、音乐识别、情感分析等功能。

## ✨ 主要功能

- 🎤 **智能语音交互** - 支持实时语音识别和语音合成
- 🎵 **音乐识别** - 基于 ACRCloud 的音乐识别和分析
- 🧠 **智能对话** - 集成多个 LLM 模型（SiliconFlow、百度、智谱等）
- 💾 **记忆系统** - 持久化对话历史和用户偏好
- 🔍 **RAG 检索** - 基于向量数据库的知识检索
- 📱 **ESP32 集成** - 支持硬件设备远程控制
- 🎭 **情感分析** - 智能情感识别和响应
- 🌐 **Web 界面** - 提供友好的 Web 管理界面

## 🏗️ 系统架构

```
SmartSisi/
├── sisi_brain/          # 核心 AI 处理模块
├── sisi_memory/         # 记忆和对话历史
├── sisi_rag/            # RAG 检索系统
├── llm/                 # LLM 集成模块
├── asr/                 # 语音识别
├── tts/                 # 语音合成
├── esp32_liusisi/       # ESP32 硬件集成
├── evoliu/              # 柳叶公会系统
└── webui/               # Web 管理界面
```

## 🚀 快速开始

### 1. 环境要求

- Python 3.8+
- Node.js 14+ (用于 Web 界面)
- Redis (可选，用于缓存)

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置

复制示例配置文件并填入你的 API 密钥：

```bash
# 复制主配置文件
cp system.conf.example system.conf

# 复制 Web 界面配置
cp webui/.env.example webui/.env
```

编辑 `system.conf` 和 `webui/.env`，填入你的 API 密钥。

### 4. 运行

```bash
# 启动主程序
python main.py

# 启动 Web 界面
cd webui
npm install
npm start
```

## ⚙️ 配置说明

### API 密钥配置

在 `system.conf` 中配置以下 API 密钥：

- **SiliconFlow API** - 用于 LLM 推理
- **百度 API** - 用于语音识别和合成
- **ACRCloud API** - 用于音乐识别
- **智谱 AI API** - 用于对话生成
- **Telegram Bot Token** - 用于 Telegram 集成（可选）

详细配置说明请参考 `system.conf.example`。

## 🔒 安全提示

⚠️ **重要：本项目不包含任何 API 密钥或敏感配置**

使用前请：

1. 复制 `system.conf.example` 为 `system.conf`
2. 复制 `webui/.env.example` 为 `webui/.env`
3. 填入你自己的 API 密钥

**切勿将包含真实密钥的配置文件提交到 Git！**

## 📁 项目结构

- `sisi_brain/` - AI 核心处理逻辑
  - `sisi_human_prompt_generator.py` - 人性化提示词生成
  - `music_humanized_processor.py` - 音乐偏好分析
  - `acrcloud_music_analyzer.py` - 音乐识别
- `sisi_memory/` - 记忆系统
- `sisi_rag/` - RAG 检索系统
- `llm/` - LLM 集成
  - `audio_context_processor.py` - 音频上下文处理
- `esp32_liusisi/` - ESP32 硬件适配器
- `evoliu/` - 柳叶公会智能体系统
- `webui/` - Web 管理界面

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 👤 作者

**xixii** - [ahaocd](https://github.com/ahaocd)

## 🙏 致谢

感谢所有开源项目和 API 服务提供商的支持。

---

**注意：** 本项目仅供学习和研究使用，请遵守相关 API 服务商的使用条款。
