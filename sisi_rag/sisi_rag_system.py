#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Sisi RAG系统 - 使用前脑系统配置
功能：知识检索增强生成，使用您配置的Qwen/Qwen3-30B-A3B模型
"""

import json
import time
import logging
import configparser
from typing import Dict, Any, List, Optional
from pathlib import Path
import requests

# 设置日志
rag_logger = logging.getLogger(__name__)

class SisiRAGSystem:
    """🔍 Sisi RAG系统 - 使用前脑系统配置"""
    
    def __init__(self, config_path: str = "system.conf"):
        self.logger = rag_logger
        
        # 读取前脑系统配置
        self.config = configparser.ConfigParser()
        self.config.read(config_path, encoding='utf-8')
        
        # 从system.conf读取RAG系统配置
        self.api_key = self.config.get('key', 'rag_llm_api_key', fallback='')
        self.base_url = self.config.get('key', 'rag_llm_base_url', fallback='https://api.siliconflow.cn/v1')
        self.model = self.config.get('key', 'rag_llm_model', fallback='Qwen/Qwen3-30B-A3B')
        self.embedding_model = self.config.get('key', 'rag_embedding_model', fallback='Qwen/Qwen3-Embedding-8B')
        
        # RAG系统配置
        self.temperature = 0.2
        self.max_tokens = 3000
        
        # 初始化向量数据库 - 🔧 修复路径冲突，使用独立的RAG数据库
        self.vector_db_path = Path(__file__).parent.parent / "sisi_rag" / "data" / "rag_chroma_db"
        self.vector_db_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化状态
        self.initialized = False
        self.collection = None
        
        self._init_vector_db()
        
        self.logger.info(f"✅ Sisi RAG系统初始化完成 - 模型: {self.model}")
    
    def _init_vector_db(self):
        """初始化向量数据库"""
        try:
            import chromadb
            from chromadb.config import Settings
            
            # 创建ChromaDB客户端
            self.client = chromadb.PersistentClient(
                path=str(self.vector_db_path),
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # 获取或创建集合
            self.collection = self.client.get_or_create_collection(
                name="sisi_knowledge",
                metadata={"description": "Sisi知识库"}
            )
            
            self.initialized = True
            self.logger.info("✅ ChromaDB向量数据库初始化成功")
            
        except ImportError:
            self.logger.warning("⚠️ ChromaDB未安装，RAG功能将受限")
            self.initialized = False
        except Exception as e:
            self.logger.error(f"❌ ChromaDB初始化失败: {e}")
            self.initialized = False
    
    def retrieve_context(self, query: str, speaker_id: str = None, top_k: int = 5) -> Dict[str, Any]:
        """检索相关上下文"""
        try:
            if not self.initialized:
                return self._fallback_context(query)
            
            # 检索相关文档
            results = self.collection.query(
                query_texts=[query],
                n_results=top_k,
                include=['documents', 'metadatas', 'distances']
            )
            
            if not results['documents'] or not results['documents'][0]:
                return self._fallback_context(query)
            
            # 构建上下文
            context_docs = []
            for i, doc in enumerate(results['documents'][0]):
                metadata = results['metadatas'][0][i] if results['metadatas'][0] else {}
                distance = results['distances'][0][i] if results['distances'][0] else 1.0
                
                context_docs.append({
                    'content': doc,
                    'metadata': metadata,
                    'relevance_score': 1.0 - distance,
                    'source': metadata.get('source', 'unknown')
                })
            
            return {
                'query': query,
                'context_documents': context_docs,
                'total_results': len(context_docs),
                'retrieval_time': time.time()
            }
            
        except Exception as e:
            self.logger.error(f"❌ 上下文检索失败: {e}")
            return self._fallback_context(query)
    
    def generate_rag_response(self, query: str, context: Dict[str, Any], speaker_id: str = None) -> str:
        """基于检索到的上下文生成回答"""
        try:
            # 构建RAG提示词
            rag_prompt = self._build_rag_prompt(query, context, speaker_id)
            
            # 调用前脑系统配置的模型
            response = self._call_llm(rag_prompt)
            
            return response
            
        except Exception as e:
            self.logger.error(f"❌ RAG回答生成失败: {e}")
            return "抱歉，我暂时无法基于知识库回答这个问题。"
    
    def _build_rag_prompt(self, query: str, context: Dict[str, Any], speaker_id: str = None) -> str:
        """构建RAG提示词 - 符合人类前脑特征"""
        
        # 整理上下文文档
        context_text = ""
        if context.get('context_documents'):
            for i, doc in enumerate(context['context_documents'], 1):
                relevance = doc.get('relevance_score', 0.0)
                source = doc.get('source', 'unknown')
                content = doc.get('content', '')
                
                context_text += f"""
文档{i} (相关度: {relevance:.2f}, 来源: {source}):
{content}

"""
        
        # 个性化信息
        user_context = ""
        if speaker_id:
            user_context = f"用户ID: {speaker_id}\n"
        
        # 构建符合人类前脑特征的RAG提示词
        prompt = f"""你是Sisi的知识整合专家，具备人类前脑的知识处理特征。

### 🧠 人类前脑知识处理特征
1. **知识关联**: 自然地将多个知识点关联起来
2. **个性化表达**: 用Sisi的语言风格表达知识
3. **不确定性处理**: 诚实表达知识边界和不确定性
4. **情感共鸣**: 理解用户的情感需求，提供温暖的回应
5. **记忆整合**: 将新知识与已有记忆自然整合

### 📚 检索到的相关知识
{context_text}

### 👤 用户信息
{user_context}

### ❓ 用户问题
{query}

### 📝 回答要求
请基于以上知识，用Sisi的人性化风格回答用户问题：
- 如果知识充分，给出详细准确的回答
- 如果知识不足，诚实说明并提供可能的方向
- 保持Sisi的温暖、理解、共情的特质
- 自然地整合多个知识点，避免生硬的列举
- 适当表达不确定性，如"我觉得"、"可能是"、"据我了解"

请回答："""
        
        return prompt
    
    def _call_llm(self, prompt: str) -> str:
        """调用前脑系统配置的LLM"""
        
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }
        
        data = {
            'model': self.model,
            'messages': [
                {
                    'role': 'system',
                    'content': '你是Sisi的知识整合专家，擅长将检索到的知识用人性化的方式表达给用户。'
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            'temperature': self.temperature,
            'max_tokens': self.max_tokens
        }
        
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            return result['choices'][0]['message']['content']
        else:
            raise Exception(f"API调用失败: {response.status_code} - {response.text}")
    
    def _fallback_context(self, query: str) -> Dict[str, Any]:
        """备用上下文"""
        return {
            'query': query,
            'context_documents': [],
            'total_results': 0,
            'retrieval_time': time.time(),
            'fallback': True
        }
    
    def add_knowledge(self, content: str, metadata: Dict[str, Any] = None) -> bool:
        """添加知识到向量数据库"""
        try:
            if not self.initialized:
                self.logger.warning("⚠️ 向量数据库未初始化，无法添加知识")
                return False
            
            # 生成唯一ID
            doc_id = f"doc_{int(time.time() * 1000)}"
            
            # 添加到集合
            self.collection.add(
                documents=[content],
                metadatas=[metadata or {}],
                ids=[doc_id]
            )
            
            self.logger.info(f"✅ 知识添加成功: {doc_id}")
            return True
            
        except Exception as e:
            self.logger.error(f"❌ 知识添加失败: {e}")
            return False
    
    def get_status(self) -> Dict[str, Any]:
        """获取RAG系统状态"""
        status = {
            'initialized': self.initialized,
            'model': self.model,
            'embedding_model': self.embedding_model,
            'vector_db_path': str(self.vector_db_path),
            'api_base_url': self.base_url
        }
        
        if self.initialized and self.collection:
            try:
                count = self.collection.count()
                status['knowledge_count'] = count
            except:
                status['knowledge_count'] = 'unknown'
        
        return status

# 全局实例
_rag_system = None

def get_rag_system() -> SisiRAGSystem:
    """获取RAG系统实例"""
    global _rag_system
    if _rag_system is None:
        _rag_system = SisiRAGSystem()
    return _rag_system

def rag_retrieve_and_generate(query: str, speaker_id: str = None) -> str:
    """便捷函数：检索并生成回答"""
    rag = get_rag_system()
    context = rag.retrieve_context(query, speaker_id)
    return rag.generate_rag_response(query, context, speaker_id)

if __name__ == "__main__":
    # 测试代码
    rag = get_rag_system()
    
    # 测试状态
    status = rag.get_status()
    print(f"📊 RAG系统状态: {json.dumps(status, indent=2, ensure_ascii=False)}")
    
    # 测试检索
    test_query = "如何处理噪音环境中的对话"
    context = rag.retrieve_context(test_query)
    print(f"🔍 检索结果: {json.dumps(context, indent=2, ensure_ascii=False)}")
    
    # 测试生成
    response = rag.generate_rag_response(test_query, context)
    print(f"💬 生成回答: {response}")
