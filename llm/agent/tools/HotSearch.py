import requests
import json
import time
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool

class HotSearchInput(BaseModel):
    """热搜查询工具的输入参数"""
    keyword: str = Field(
        default="成都",
        description="筛选关键词，默认为'成都'，用于筛选出包含该关键词的热搜"
    )

class HotSearch(BaseTool):
    """抖音热搜查询工具，符合官方工具调用规范"""
    name: str = "hot_search"
    description: str = "查询抖音最新热搜话题的工具。返回第2、3条热搜和包含关键词(默认为'成都')的热搜。"
    args_schema: type[BaseModel] = HotSearchInput
    
    # 天行数据API密钥
    _api_key: str = "2724c89256901d191d53df0dc33b8d25"
    
    # 抖音热搜API
    _api_url: str = "https://apis.tianapi.com/douyinhot/index"
    
    # 缓存
    _cache = []
    _cache_time = 0
    _cache_expire = 180  # 缓存有效期3分钟

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None, api_key: Optional[str] = None):
        """初始化热搜工具"""
        tool_params = {}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
            
        if api_key is not None:
            self._api_key = api_key
            
        super().__init__(**tool_params)

    async def _arun(self, keyword: str = "成都") -> str:
        """异步查询热搜"""
        return self._run(keyword)

    def _run(self, keyword: str = "成都") -> str:
        """
        查询抖音热搜榜单，返回第2、3条和包含关键词的热搜
        
        Args:
            keyword: 筛选关键词，默认为'成都'
            
        Returns:
            str: 格式化的热搜榜单文本
        """
        # 检查缓存
        current_time = time.time()
        if self._cache and current_time - self._cache_time < self._cache_expire:
            # 使用缓存数据
            hot_list = self._cache
        else:
            # 准备请求参数
            params = {
                "key": self._api_key
            }
            
            try:
                # 发送请求
                response = requests.get(self._api_url, params=params, timeout=5)
                
                # 检查响应状态
                if response.status_code != 200:
                    return f"请求失败，状态码: {response.status_code}"
                    
                # 解析响应数据
                result = response.json()
                
                # 检查API返回状态
                if result.get("code") != 200:
                    return f"API调用失败: {result.get('msg', '未知错误')}"
                    
                # 提取热搜列表
                hot_list = result.get("result", {}).get("list", [])
                
                # 更新缓存
                self._cache = hot_list
                self._cache_time = current_time
                
            except requests.Timeout:
                return "请求超时，请稍后再试"
            except Exception as e:
                return f"查询热搜时发生错误: {str(e)}"
        
        # 格式化输出
        if not hot_list:
            return "未找到抖音热搜数据"
            
        return self._format_filtered_hot_list(hot_list, keyword)
    
    def _format_filtered_hot_list(self, hot_list: List[Dict], keyword: str) -> str:
        """格式化筛选后的热搜列表为纯文本"""
        if not hot_list:
            return "暂无抖音热搜数据"
            
        # 构建输出
        output = "【抖音热搜精选】\n"
        
        # 添加第2和第3条热搜
        if len(hot_list) >= 3:
            for i in [1, 2]:  # 索引1和2对应第2和第3条
                item = hot_list[i]
                word = item.get("word", "")
                hot_index = item.get("hotindex", "")
                hot_index_text = f"热度:{hot_index}" if hot_index else ""
                
                output += f"{i+1}. {word}"
                if hot_index_text:
                    output += f" ({hot_index_text})"
                output += "\n"
        
        # 添加包含关键词的热搜
        if keyword:
            keyword_items = []
            for i, item in enumerate(hot_list):
                word = item.get("word", "")
                if keyword.lower() in word.lower() and i not in [1, 2]:  # 排除已添加的2、3条
                    hot_index = item.get("hotindex", "")
                    hot_index_text = f"热度:{hot_index}" if hot_index else ""
                    
                    item_text = f"* {word}"
                    if hot_index_text:
                        item_text += f" ({hot_index_text})"
                    
                    keyword_items.append(item_text)
            
            if keyword_items:
                output += f"\n包含「{keyword}」的热搜：\n"
                output += "\n".join(keyword_items)
            else:
                output += f"\n未找到包含「{keyword}」的热搜"
        
        return output.strip()

if __name__ == "__main__":
    # 测试热搜工具
    hot_search = HotSearch()
    
    # 测试抖音热搜（仅获取第2、3条）
    print("\n抖音热搜精选:")
    result_douyin = hot_search._run("")
    print(result_douyin)
    
    # 测试抖音热搜（包含关键词'成都'）
    print("\n抖音成都相关热搜:")
    result_douyin_chengdu = hot_search._run("成都")
    print(result_douyin_chengdu) 