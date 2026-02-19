from typing import Optional
# 移除langchain默认搜索工具依赖
# from langchain_community.tools.ddg_search import DuckDuckGoSearchRun
from langchain.tools import BaseTool
from pydantic import BaseModel, Field
import time  # 添加time模块用于模拟延迟

class SearchInput(BaseModel):
    """搜索输入参数"""
    query: str = Field(..., description="要搜索的查询内容")

class SearchTool(BaseTool):
    name: str = "search_web"
    description: str = "搜索互联网上的信息。输入应该是一个搜索查询。"
    args_schema: type[BaseModel] = SearchInput

    def _run(self, query: str) -> str:
        """运行搜索"""
        try:
            # 已移除默认搜索工具，返回提示信息
            time.sleep(1)  # 短暂延迟模拟搜索过程
            return f"搜索功能已关闭，请使用其他工具。您搜索的内容是：{query}"
        except Exception as e:
            return f"搜索出错: {str(e)}"

    async def _arun(self, query: str) -> str:
        """异步运行搜索"""
        return self._run(query)

# 装饰器版本
from langchain.tools import tool

@tool
def search_web(query: str) -> str:
    """搜索互联网上的信息（已关闭）"""
    # 已移除默认搜索工具，返回提示信息
    time.sleep(1)  # 短暂延迟模拟搜索过程
    return f"搜索功能已关闭，请使用其他工具。您搜索的内容是：{query}"

if __name__ == "__main__":
    # 测试代码
    search_tool = SearchTool()
    result = search_tool.run("Python programming language")
    print(result) 