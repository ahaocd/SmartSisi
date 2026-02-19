# 🔍 Sisi RAG系统

## 📋 目标
RAG检索增强生成系统，为Sisi提供智能检索和上下文增强能力，基于2025年最火的LangChain框架。

## 🎯 核心功能
- **向量检索**：ChromaDB向量数据库存储
- **智能检索**：基于语义相似度的内容检索
- **上下文增强**：为LLM提供相关背景信息
- **多模态支持**：文本、音频元数据检索

## 📊 最近改动
- ✅ 2025-07-20: 创建sisi_rag文件夹
- ❌ 待完成: LangChain RAG系统集成
- ❌ 待完成: ChromaDB向量数据库
- ❌ 待完成: 检索器实现

## 📈 进度
**0%** - 需要克隆LangChain和ChromaDB，创建核心文件

## 📁 文件结构
```
sisi_rag/
├── README.md              # 本文档
├── sisi_langchain.py      # ❌ LangChain RAG系统 (待创建)
├── sisi_chroma.py         # ❌ ChromaDB向量数据库 (待创建)
├── sisi_retriever.py      # ❌ 检索器 (待创建)
└── models/                # ❌ 需要克隆的模型文件
    ├── embeddings/        # 嵌入模型
    └── vectorstore/       # 向量存储
```

## 🔧 技术栈
- **LangChain**: 2025年最火RAG框架 (持续更新)
- **ChromaDB**: 轻量级向量数据库
- **SentenceTransformers**: 文本嵌入模型
- **Faiss**: 高速相似性搜索

## 🚀 需要克隆的项目
```bash
# LangChain
git clone https://github.com/langchain-ai/langchain.git

# ChromaDB  
git clone https://github.com/chroma-core/chroma.git

# SentenceTransformers模型
# 需要下载预训练模型
```

## 🎯 为三个模块服务
1. **快速响应模块** - 提供快速相关信息检索
2. **优化站** - 基于RAG增强回应质量
3. **订阅站** - 检索相关补充内容

## ⚠️ 依赖问题
**您说得对！需要克隆以下项目：**
- LangChain框架本身
- ChromaDB数据库
- 预训练嵌入模型
- 向量存储配置

## 🔄 下一步计划
1. **克隆必要项目** - LangChain, ChromaDB
2. **下载预训练模型** - 嵌入模型
3. **创建RAG核心文件**
4. **集成到Sisi系统**

## 💡 重要提醒
RAG系统不是简单的pip install，需要：
- 克隆源码项目
- 下载预训练模型
- 配置向量数据库
- 设置检索参数
