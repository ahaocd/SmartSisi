#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
🔍 Sisi RAG检索系统
基于ChromaDB和LangChain的检索增强生成系统
"""

import os
import sys
import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import hashlib

# 添加项目路径
sys.path.append(str(Path(__file__).parent.parent))

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SisiRAGRetriever:
    """🔍 Sisi RAG检索器"""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent
        self.vector_db_path = self.base_dir.parent / "sisi_memory" / "data" / "chroma_db"
        self.vector_db_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化状态
        self.initialized = False
        self.collection = None
        self.embedding_model = None
        
        logger.info(f"🔍 Sisi RAG检索器初始化")
        logger.info(f"   📁 向量数据库路径: {self.vector_db_path}")
        
        # 尝试初始化ChromaDB
        self._init_chroma_db()
    
    def _init_chroma_db(self):
        """初始化ChromaDB"""
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
            logger.info("✅ ChromaDB初始化成功")
            
        except ImportError:
            logger.warning("⚠️ ChromaDB未安装，RAG功能将受限")
            self.initialized = False
        except Exception as e:
            logger.error(f"❌ ChromaDB初始化失败: {e}")
            self.initialized = False
    
    def is_available(self) -> bool:
        """检查RAG系统是否可用"""
        return self.initialized and self.collection is not None
    
    def add_document(self, content: str, metadata: Dict[str, Any] = None) -> str:
        """添加文档到知识库"""
        if not self.is_available():
            logger.warning("RAG系统不可用，无法添加文档")
            return ""
        
        try:
            # 生成文档ID
            doc_id = hashlib.md5(content.encode()).hexdigest()
            
            # 准备元数据
            if metadata is None:
                metadata = {}
            
            metadata.update({
                "timestamp": datetime.now().isoformat(),
                "content_length": len(content),
                "doc_id": doc_id
            })
            
            # 添加到ChromaDB
            self.collection.add(
                documents=[content],
                metadatas=[metadata],
                ids=[doc_id]
            )
            
            logger.info(f"✅ 文档已添加到知识库: {doc_id[:8]}...")
            return doc_id
            
        except Exception as e:
            logger.error(f"❌ 添加文档失败: {e}")
            return ""
    
    def search(self, query: str, n_results: int = 5) -> List[Dict[str, Any]]:
        """搜索相关文档"""
        if not self.is_available():
            logger.warning("RAG系统不可用，返回空结果")
            return []
        
        try:
            # 执行搜索
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            # 格式化结果
            formatted_results = []
            if results['documents'] and results['documents'][0]:
                for i, doc in enumerate(results['documents'][0]):
                    result = {
                        "content": doc,
                        "metadata": results['metadatas'][0][i] if results['metadatas'] and results['metadatas'][0] else {},
                        "distance": results['distances'][0][i] if results['distances'] and results['distances'][0] else 0.0,
                        "id": results['ids'][0][i] if results['ids'] and results['ids'][0] else ""
                    }
                    formatted_results.append(result)
            
            logger.info(f"🔍 搜索完成: 查询='{query}', 结果数={len(formatted_results)}")
            return formatted_results
            
        except Exception as e:
            logger.error(f"❌ 搜索失败: {e}")
            return []
    
    def get_context(self, query: str, max_context_length: int = 2000) -> str:
        """获取查询相关的上下文"""
        results = self.search(query, n_results=3)
        
        if not results:
            return ""
        
        # 构建上下文
        context_parts = []
        current_length = 0
        
        for result in results:
            content = result["content"]
            if current_length + len(content) <= max_context_length:
                context_parts.append(content)
                current_length += len(content)
            else:
                # 截断最后一个文档
                remaining_length = max_context_length - current_length
                if remaining_length > 100:  # 至少保留100字符
                    context_parts.append(content[:remaining_length] + "...")
                break
        
        context = "\n\n".join(context_parts)
        logger.info(f"📝 上下文构建完成: 长度={len(context)}")
        return context
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取RAG系统统计信息"""
        if not self.is_available():
            return {
                "available": False,
                "error": "RAG系统不可用"
            }
        
        try:
            # 获取集合信息
            collection_count = self.collection.count()
            
            return {
                "available": True,
                "document_count": collection_count,
                "collection_name": self.collection.name,
                "vector_db_path": str(self.vector_db_path),
                "initialized": self.initialized
            }
            
        except Exception as e:
            return {
                "available": False,
                "error": str(e)
            }

# 全局RAG检索器实例
_rag_retriever = None

def get_rag_retriever() -> SisiRAGRetriever:
    """获取RAG检索器实例（单例模式）"""
    global _rag_retriever
    if _rag_retriever is None:
        _rag_retriever = SisiRAGRetriever()
    return _rag_retriever

# 便捷函数
def search_knowledge(query: str, n_results: int = 5) -> List[Dict[str, Any]]:
    """搜索知识库"""
    retriever = get_rag_retriever()
    return retriever.search(query, n_results)

def add_knowledge(content: str, metadata: Dict[str, Any] = None) -> str:
    """添加知识到知识库"""
    retriever = get_rag_retriever()
    return retriever.add_document(content, metadata)

def get_knowledge_context(query: str, max_length: int = 2000) -> str:
    """获取知识上下文"""
    retriever = get_rag_retriever()
    return retriever.get_context(query, max_length)

if __name__ == "__main__":
    # 测试RAG系统
    print("🔍 测试Sisi RAG检索系统")
    
    retriever = get_rag_retriever()
    
    # 检查可用性
    print(f"系统可用: {retriever.is_available()}")
    
    # 获取统计信息
    stats = retriever.get_statistics()
    print(f"统计信息: {json.dumps(stats, ensure_ascii=False, indent=2)}")
    
    # 如果可用，进行测试
    if retriever.is_available():
        # 添加测试文档
        test_doc = "这是一个测试文档，用于验证RAG系统的功能。"
        doc_id = retriever.add_document(test_doc, {"type": "test"})
        print(f"添加文档: {doc_id}")
        
        # 搜索测试
        results = retriever.search("测试文档")
        print(f"搜索结果: {len(results)} 个")
        
        # 获取上下文
        context = retriever.get_context("RAG系统")
        print(f"上下文长度: {len(context)}")
