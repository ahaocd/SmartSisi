from typing import Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool
import requests
import json
from utils import config_util

class WebPageRetrieverInput(BaseModel):
    """网页检索的输入参数"""
    query: str = Field(
        ..., 
        description="要检索的查询词或问题"
    )
    result_count: int = Field(
        default=5, 
        description="返回的结果数量"
    )

class WebPageRetriever(BaseTool):
    """Bing搜索API网页检索工具"""
    name: str = "web_page_retriever"
    description: str = "通过Bing搜索API快速检索和获取与特定查询词条相关的网页信息"
    args_schema: type[BaseModel] = WebPageRetrieverInput

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        """初始化网页检索工具"""
        tool_params = {}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
            
        super().__init__(**tool_params)

    async def _arun(self, query: str, result_count: int = 5) -> str:
        """异步检索网页信息"""
        return self._run(query, result_count)

    def _run(self, query: str, result_count: int = 5) -> str:
        """
        检索网页信息
        
        Args:
            query: 要检索的查询词或问题
            result_count: 返回的结果数量
            
        Returns:
            str: 格式化的搜索结果
        """
        # 尝试从配置中获取API密钥
        subscription_key = getattr(config_util, "bing_search_api_key", "")
        
        # 如果配置中没有，则使用空字符串
        if not subscription_key:
            return '请在system.conf中配置bing_search_api_key'

        url = "https://api.bing.microsoft.com/v7.0/search"
        headers = {'Ocp-Apim-Subscription-Key': subscription_key}
        params = {
            'q': query, 
            'mkt': 'zh-CN',  # 使用中文结果
            'count': min(result_count, 10)  # 限制最大结果数为10
        }

        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()  
            data = response.json()  
            web_pages = data.get('webPages', {})
            
            # 将字典转换为格式化的字符串
            if 'value' in web_pages and web_pages['value']:
                results = []
                for i, page in enumerate(web_pages['value'][:result_count]):
                    title = page.get('name', '无标题')
                    snippet = page.get('snippet', '无描述')
                    url = page.get('url', '#')
                    results.append(f"{i+1}. {title}\n   {snippet}\n   链接: {url}")
                
                return f"关于「{query}」的搜索结果:\n\n" + "\n\n".join(results)
            else:
                return f"未找到关于「{query}」的搜索结果"
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            if status_code == 401:
                return "认证失败：API密钥无效或已过期"
            elif status_code == 403:
                return "权限不足：没有使用该API的权限"
            elif status_code == 429:
                return "请求频率过高：超出API调用限制"
            else:
                return f"HTTP错误: {status_code} - {e.response.reason}"
        except requests.exceptions.ConnectionError:
            return "连接错误：无法连接到Bing API服务器"
        except requests.exceptions.Timeout:
            return "请求超时：Bing API响应时间过长"
        except Exception as e:
            return f'搜索查询失败: {str(e)}'


if __name__ == "__main__":
    tool = WebPageRetriever()
    result = tool._run("归纳一下近年关于'经济发展'的论文的特点和重点")
    print(result)
    
    # 测试自定义结果数量
    print(tool._run("人工智能最新进展", 3))
