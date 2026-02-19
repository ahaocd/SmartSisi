import requests
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool
from .base_tool import SisiBaseTool
import json
from utils import config_util
import logging

class GoogleSearchInput(BaseModel):
    """Google搜索的输入参数"""
    query: str = Field(
        ...,
        description="要在Google上搜索的关键词"
    )
    num: int = Field(
        default=5,
        description="返回的最大结果数(1-10)"
    )
    page: int = Field(
        default=1,
        description="结果页码"
    )

class GoogleSearch(SisiBaseTool):
    """
    Google搜索工具，使用API进行网络搜索
    """
    name: str = "google_search"
    description: str = "通过Google搜索引擎检索网络信息。输入要搜索的关键词，返回相关网页的标题、链接和摘要。"
    args_schema: type[BaseModel] = GoogleSearchInput
    uid: int = 0
    
    def __init__(self, uid: int = 0, name: Optional[str] = None, description: Optional[str] = None):
        """
        初始化Google搜索工具
        
        Args:
            uid: 用户ID
            name: 可选的工具名称
            description: 可选的工具描述
        """
        tool_params = {"uid": uid}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
        
        super().__init__(**tool_params)
        
    def _run(self, query: str, num: int = 5, page: int = 1) -> str:
        """
        执行Google搜索
        
        Args:
            query: 搜索关键词
            num: 每页结果数量，最大10
            page: 页码，从1开始
            
        Returns:
            格式化的搜索结果
        """
        api_key = config_util.google_search_api_key
        api_base = config_util.google_search_api_base
        
        if not api_key or not api_base:
            return "Google搜索API未配置，请在system.conf中设置google_search_api_key和google_search_api_base"
        
        # 构建API请求
        api_url = f"{api_base}/plugins/google-search"
        
        params = {
            "query": query,
            "num": min(num, 10),  # 确保不超过最大值
            "page": max(page, 1)   # 确保不低于最小值
        }
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(api_url, params=params, headers=headers)
            response.raise_for_status()
            results = response.json()
            
            # 格式化结果
            formatted_results = f"Google搜索「{query}」的结果:\n\n"
            
            if "items" in results and results["items"]:
                for i, item in enumerate(results["items"]):
                    formatted_results += f"{i+1}. {item.get('title', '无标题')}\n"
                    formatted_results += f"   链接: {item.get('link', '无链接')}\n"
                    formatted_results += f"   摘要: {item.get('snippet', '无摘要')}\n\n"
            else:
                formatted_results += "未找到相关结果。\n"
            
            return formatted_results
        except Exception as e:
            logging.error(f"Google搜索失败: {str(e)}")
            return f"搜索失败: {str(e)}"

    async def _arun(self, query: str, num: int = 5, page: int = 1) -> str:
        """
        异步执行Google搜索
        
        Args:
            query: 搜索关键词
            num: 每页结果数量，最大10
            page: 页码，从1开始
            
        Returns:
            格式化的搜索结果
        """
        return self._run(query, num, page)


# 测试代码
if __name__ == "__main__":
    # 设置测试用的API密钥
    config_util.google_search_api_key = "your-api-key-here"
    config_util.google_search_api_base = "your-api-base-here"
    
    tool = GoogleSearch()
    result = tool._run("Python编程入门教程")
    print(result)
