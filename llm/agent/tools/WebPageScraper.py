from bs4 import BeautifulSoup
from typing import Any, Optional
from pydantic import BaseModel, Field
from langchain_core.tools import BaseTool, tool
import requests

class WebPageScraperInput(BaseModel):
    """网页抓取的输入参数"""
    url: str = Field(
        ...,
        description="要抓取的网页URL，必须以http://或https://开头"
    )
    max_length: int = Field(
        default=1500,
        description="返回的最大内容长度"
    )

class WebPageScraper(BaseTool):
    """网页内容抓取工具"""
    name: str = "web_page_scraper"
    description: str = "获取网页内容，提取标题和主要文本。输入网页地址，如：https://www.baidu.com/"
    args_schema: type[BaseModel] = WebPageScraperInput

    def __init__(self, name: Optional[str] = None, description: Optional[str] = None):
        """初始化网页抓取工具"""
        tool_params = {}
        if name is not None:
            tool_params["name"] = name
        if description is not None:
            tool_params["description"] = description
            
        super().__init__(**tool_params)

    async def _arun(self, url: str, max_length: int = 1500) -> str:
        """异步抓取网页内容"""
        return self._run(url, max_length)

    def _run(self, url: str, max_length: int = 1500) -> str:
        """
        抓取网页内容
        
        Args:
            url: 要抓取的网页URL，必须以http://或https://开头
            max_length: 返回的最大内容长度
            
        Returns:
            str: 网页标题和内容摘要
        """
        # 验证URL格式
        if not url.startswith(('http://', 'https://')):
            return "URL格式错误，必须以http://或https://开头"
            
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=10, verify=True)
            response.raise_for_status()  # 检查请求是否成功
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 提取网页标题
            title = soup.title.string if soup.title else "无标题"
            
            # 提取主要文本内容
            # 移除script和style元素
            for script in soup(["script", "style"]):
                script.extract()
                
            # 获取文本
            text = soup.get_text(strip=True)
            
            # 对长文本进行截断
            if len(text) > max_length:
                text = text[:max_length] + "...(内容过长已截断)"
                
            # 构建格式化的返回结果
            result = f"网页标题: {title}\n\n网页内容摘要:\n{text}"
            return result
        except requests.exceptions.SSLError:
            return 'SSL证书验证失败，无法安全连接到该网站'
        except requests.exceptions.Timeout:
            return '请求超时，网站响应时间过长'
        except requests.exceptions.ConnectionError:
            return '连接错误，无法连接到指定网站'
        except requests.exceptions.HTTPError as e:
            return f'HTTP错误: {e.response.status_code} - {e.response.reason}'
        except Exception as e:
            return f'无法获取该网页内容: {str(e)}'
        
if __name__ == "__main__":
    tool = WebPageScraper()
    result = tool._run("https://book.douban.com/review/14636204")
    print(result)
    
    # 测试错误URL
    print(tool._run("invalid-url"))
    
    # 测试自定义长度
    print(tool._run("https://www.baidu.com", 200))