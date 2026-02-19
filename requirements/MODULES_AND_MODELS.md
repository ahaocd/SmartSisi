# SmartSisi 系统模块与模型文档

## 系统概览

SmartSisi系统由多个核心模块组成，每个模块使用不同的模型和依赖库来实现特定功能。本系统基于ESP32设备端和PC服务器端架构，通过WebSocket协议进行通信。

## 核心模块与模型

### 1. 语音识别模块 (ASR)

**模块位置**: `SmartSisi/asr/`

**主要模型**:
- **SenseVoice** (funasr): 多语言语音理解模型
  - 功能: 语音识别(ASR)、语种识别(LID)、语音情感识别(SER)、声学事件检测(AED)
  - 模型大小: Small版本
  - 使用场景: 实时语音转文本、音频上下文分析

**依赖库**:
- funasr>=0.8.0
- modelscope>=1.10.0
- torch>=1.10.1
- torchaudio>=0.10.1

### 2. 声纹识别模块

**模块位置**: `SmartSisi/asr/3D-Speaker/`

**主要模型**:
- **3D-Speaker**: 多模态说话人识别项目
  - 功能: 声纹识别、说话人验证、语种识别
  - 特点: 结合声学、语义和视觉信息
  - 使用场景: 用户身份识别、个性化服务

**依赖库**:
- torch>=1.10.1
- torchaudio>=0.10.1
- scipy>=1.7.0
- numpy>=1.20.0,<1.24
- scikit-learn==1.0.2

### 3. 前脑系统模块

**模块位置**: `SmartSisi/sisi_brain/`

**主要模型**:
- **记忆系统LLM**: Qwen/Qwen2.5-14B-Instruct
  - 功能: 用户记忆管理、个性化存储
  - 服务提供商: SiliconFlow
  - API密钥配置: `memory_llm_api_key` in system.conf

- **RAG系统LLM**: Qwen/Qwen2.5-14B-Instruct
  - 功能: 知识检索增强生成
  - 嵌入模型: Qwen/Qwen3-Embedding-8B
  - 服务提供商: SiliconFlow

- **音频数据分析模型**: Qwen/Qwen3-8B
  - 功能: 交互音频数据分析
  - 服务提供商: SiliconFlow

- **动态提示词模型**: GLM-4.5-X
  - 功能: 动态提示词生成
  - 服务提供商: Zhipu AI (智谱AI)

**依赖库**:
- openai (用于调用SiliconFlow API)
- chromadb (向量数据库)
- requests

### 4. 记忆系统模块

**模块位置**: `SmartSisi/sisi_memory/`

**主要模型**:
- **记忆系统LLM**: Qwen/Qwen2.5-14B-Instruct
  - 功能: 用户级记忆、会话级记忆、智能体记忆
  - 服务提供商: SiliconFlow
  - 嵌入模型: BAAI/bge-large-zh-v1.5

**依赖库**:
- mem0 (核心记忆框架)
- chromadb (本地向量数据库)
- sqlite3 (历史数据库)

### 5. RAG系统模块

**模块位置**: `SmartSisi/sisi_rag/`

**主要模型**:
- **RAG系统LLM**: Qwen/Qwen3-30B-A3B
  - 功能: 知识检索增强生成
  - 嵌入模型: Qwen/Qwen3-Embedding-8B
  - 服务提供商: SiliconFlow

**依赖库**:
- chromadb (向量数据库)
- openai (用于调用SiliconFlow API)

### 6. Agent系统模块

**模块位置**: `SmartSisi/llm/agent/`

**主要组件**:
- **SisiAgentCore**: Agent核心实现，使用LangGraph处理工具调用和交互
- **A2A集成**: 提供与外部工具和服务的集成能力
- **工具节点**: 处理特定任务的工具集合

**功能**:
- 工具调用和执行
- 对话管理和状态跟踪
- 外部服务集成
- 自动化任务执行

**依赖库**:
- langgraph (核心工作流引擎)
- langchain-core (消息处理)
- openai (API调用)
- requests (HTTP请求)

### 7. Liuye系统模块

**模块位置**: `SmartSisi/evoliu/liuye_decision_center/` 和 `SmartSisi/evoliu/liuye_frontend/`

**主要组件**:
- **IntelligentLiuye**: 智能柳叶核心实现，提供智能对话、TTS语音、Web界面等功能
- **IntelligentAgents**: 柳叶智能体推理引擎，基于LlamaIndex ReActAgent实现意图分析、工具选择、质量监督
- **LlamaIndexNativeOrchestrator**: 纯真实API智能体编排器，专注于双模型决策中枢集成

**功能**:
- 智能对话处理
- 情感触发器处理
- TTS语音生成和播放
- Web界面管理
- AI工具监督和质量控制
- 意图理解和任务分解

**依赖库**:
- llama-index-core (智能体引擎)
- openai (API调用)
- pygame (音频播放)
- fastapi (Web界面)
- uvicorn (Web服务器)

### 8. 音频处理模块

**模块位置**: `SmartSisi/esp32_liusisi/`

**主要组件**:
- **Opus编码器**: OPUS格式音频编解码
  - 采样率: 16000Hz
  - 位深度: 16位
  - 格式: OPUS

- **音频输出管理器**: 流式音频传输
  - 功能: 队列管理、边界标记处理

**依赖库**:
- opuslib>=3.0.1
- pydub
- pyaudio~=0.2.11

### 9. ESP32设备端模块

**模块位置**: `SmartSisi/sisi-mini/`

**主要组件**:
- **ESP-IDF框架**: 版本v5.3.1
- **ESP-Opus组件**: OPUS音频编解码
- **ESP-SR组件**: 语音识别支持

**依赖库**:
- ESP-IDF v5.3.1
- esp-opus库
- esp-sr库

## 服务提供商与API

### SiliconFlow
- **服务类型**: 大模型API服务平台
- **支持模型**: Qwen系列、GLM系列等
- **特点**: 按量计费、支持多种开源模型

### 配置文件位置
- 主配置文件: `SmartSisi/system.conf`
- API密钥配置项: 各模块对应的api_key字段

## 网络端口配置

系统使用多个固定端口:
- 5000: Web管理界面
- 10001: ESP32 TCP通信
- 10002: 数字人接口
- 10003: UI数据接口
- 10197: ASR服务端口
- 6000: 自动播放服务
- 9001: WebSocket-TCP桥接

## 部署要求

### 本地部署
- **CPU**: Intel i5/AMD Ryzen 5及以上
- **内存**: 16GB RAM
- **存储**: 50GB SSD存储
- **操作系统**: Windows 10/11或Ubuntu 18.04+

### 云服务器部署
- **支持平台**: 阿里云、腾讯云、AWS、Azure
- **操作系统**: CentOS 7或Ubuntu 18.04+
- **注意**: Windows系统仅支持本地部署

## 模型存储位置

1. **FUNASR模型**: 
   - 位置: `C:\Users\用户名\.cache\modelscope\hub\models\iic\`
   - 包含: SenseVoiceSmall模型文件

2. **3D-Speaker模型**:
   - 位置: `SmartSisi/asr/3D-Speaker/pretrained_models/`
   - 包含: CAM++说话人识别模型

3. **RAG向量数据库**:
   - 位置: `SmartSisi/sisi_rag/data/rag_chroma_db/`

4. **记忆系统数据库**:
   - 位置: `SmartSisi/sisi_memory/data/chroma_db/`
   - 历史数据库: `SmartSisi/sisi_memory/data/sisi_memory_history.db`

## 依赖库管理

所有依赖库文件已整理到`SmartSisi/requirements/`目录下:
- `requirements_all.txt`: 完整依赖库清单
- `requirements_main.txt`: 主项目依赖
- `requirements_docker.txt`: Docker部署依赖
- `requirements_3dspeaker.txt`: 3D-Speaker模块依赖
- `requirements_p3_tools.txt`: P3工具依赖
- `requirements_openwebui.txt`: OpenWebUI前端依赖
- `requirements_mem0.txt`: Mem0记忆模块依赖