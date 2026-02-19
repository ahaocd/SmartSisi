"""
A2A工具集合 - 包含所有A2A标准工具
实现A2A协议所需的各类工具功�?"""

import importlib
import logging
from typing import Dict, List, Any, Optional, Union

# 配置日志
logger = logging.getLogger(__name__)

# 直接从工具文件导入
from .location_weather import LocationWeatherTool
from .music_tool import MusicGeneratorTool, create_tool as create_music_tool
from .currency import create_tool as create_currency_tool
from .sisidisk_tool import create_tool as create_sisidisk_tool
from .bai_lian_tool import create_tool as create_bailian_tool

# 导入增强版音乐工具
try:
    from .sisimusic.music_tool_enhanced import EnhancedMusicGeneratorTool, create_tool as create_enhanced_music_tool
    MusicTool = create_enhanced_music_tool()
    enhanced_music_available = True
    logger.info("成功加载增强版音乐生成工具")
except Exception as e:
    # 导入失败时使用原始版本
    MusicTool = create_music_tool()
    enhanced_music_available = False
    logger.error(f"加载增强版音乐生成工具失败: {str(e)}，将使用原始版本")

# 初始化工具实例
CurrencyTool = create_currency_tool()
SisidiskTool = create_sisidisk_tool()
BaiLianTool = create_bailian_tool()

# 统一使用 a2a_adapter 动态加载所有工具
from ..a2a_adapter import _TOOL_REGISTRY, register_tool

# 导入所有需要注册的A2A工具函数
# Import all A2A tool functions that need to be registered
from .location_weather import a2a_tool_location_weather
from .currency import a2a_tool_currency
from .zudao import a2a_tool_zudao
from .hot_search import a2a_tool_hot_search
from .music_tool import a2a_tool_music_tool
from .bailian_tool import a2a_tool_bailian
from .sisidisk_tool import a2a_tool_sisidisk_tool
from .sisieyes_tool import a2a_tool_sisieyes
from .social_auto_upload_tool import a2a_tool_social_auto_upload
from .douyin_marketing_agent_tool import a2a_tool_douyin_marketing
# from .asianight.asianight_agent_tool import a2a_tool_asianight_agent  # TODO: 待实现

# 注册所有工具
try:
    # 清理旧的注册信息，确保幂等性
    # _TOOL_REGISTRY.clear()

    # 依次注册工具，确保名称唯一
    register_tool(a2a_tool_location_weather, 'location_weather')
    register_tool(a2a_tool_currency, 'currency')
    register_tool(a2a_tool_sisidisk_tool, 'sisidisk')
    register_tool(a2a_tool_zudao, 'zudao')
    register_tool(a2a_tool_hot_search, 'hot_search')
    register_tool(a2a_tool_music_tool, 'music')
    register_tool(a2a_tool_bailian, 'bailian')
    register_tool(a2a_tool_sisieyes, 'sisieyes')

    # 注册医疗工具
    
    # 注册内容自动化智能体
    register_tool(a2a_tool_social_auto_upload, 'content_automation')
    
    # 注册抖音营销智能体
    register_tool(a2a_tool_douyin_marketing, 'douyin_marketing')
    
    # 注册ASIANIGHT内容自动化智能体 (待实现)
    # register_tool(a2a_tool_asianight_agent, 'asianight_agent')

except Exception as e:
    # 记录注册失败的日志
    logging.error(f"A2A工具注册失败 | A2A tool registration failed: {e}", exc_info=True)

# 导出所有已注册的工具名称
__all__ = list(_TOOL_REGISTRY.keys())

def create_tools() -> Dict[str, Any]:
    """创建并返回所有A2A工具"""
    tools = {}
    
    # 创建各种工具
    try:
        from .zudao import create_tool as create_zudao
        tools["zudao"] = create_zudao()
        logger.info("成功加载道法万千工具")
    except Exception as e:
        logger.error(f"加载道法万千工具错误: {str(e)}")
        
    try:
        from .bai_lian_tool import create_tool as create_bailian
        tools["bailian"] = create_bailian()
        logger.info("成功加载百炼工具")
    except Exception as e:
        logger.error(f"加载百炼工具错误: {str(e)}")
        
    try:
        from .location_weather import create_tool as create_weather
        tools["weather"] = create_weather()
        logger.info("成功加载天气工具")
    except Exception as e:
        logger.error(f"加载天气工具错误: {str(e)}")

    try:
        from .sisieyes_tool import create_tool as create_sisieyes
        tools["sisieyes"] = create_sisieyes()
        logger.info("成功加载SISIeyes工具")
    except Exception as e:
        logger.error(f"加载SISIeyes工具错误: {str(e)}")

    return tools

# 添加测试SSE响应的工具函数
async def test_sse_response(tool, query="测试查询"):
    """
    测试工具的SSE响应
    
    Args:
        tool: 要测试的A2A工具实例
        query: 测试查询字符串
        
    Returns:
        bool: 测试是否成功
    """
    import aiohttp
    import asyncio
    from aiohttp import web
    
    logger.info(f"开始测试工具 {tool.name} 的SSE响应...")
    
    # 创建一个简单的HTTP服务器来测试SSE响应
    async def handle_sse_test(request):
        """处理SSE测试请求"""
        try:
            # 生成SSE响应
            response = web.StreamResponse()
            response.headers['Content-Type'] = 'text/event-stream'
            response.headers['Cache-Control'] = 'no-cache'
            response.headers['Connection'] = 'keep-alive'
            await response.prepare(request)
            
            # 记录响应头
            logger.info(f"SSE测试服务器设置的响应头: {response.headers}")
            
            # 从工具获取SSE数据
            async for sse_data in tool.get_sse_response(query):
                # 写入SSE数据
                await response.write(f"data: {sse_data}\n\n".encode('utf-8'))
                await asyncio.sleep(0.1)  # 延迟以模拟真实情况
                
            await response.write("event: done\ndata: {}\n\n".encode('utf-8'))
            await response.write_eof()
            return response
            
        except Exception as e:
            logger.error(f"SSE测试服务器错误: {str(e)}")
            return web.Response(text=f"Error: {str(e)}", status=500)
    
    # 启动测试服务器
    app = web.Application()
    app.router.add_get('/test-sse', handle_sse_test)
    
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, 'localhost', 8099)
    await site.start()
    
    try:
        logger.info("SSE测试服务器已启动: http://localhost:8099/test-sse")
        
        # 连接到测试服务器
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8099/test-sse') as response:
                # 检查Content-Type
                content_type = response.headers.get('Content-Type', '')
                logger.info(f"收到响应，Content-Type: {content_type}")
                
                if 'text/event-stream' in content_type:
                    logger.info("响应Content-Type正确设置为text/event-stream")
                else:
                    logger.error(f"响应Content-Type不正确: {content_type}")
                
                # 读取SSE数据
                async for line in response.content:
                    line_text = line.decode('utf-8').strip()
                    if line_text:
                        logger.info(f"收到SSE数据: {line_text}")
        
        logger.info("SSE测试完成")
        return True
    except Exception as e:
        logger.error(f"连接测试服务器错误: {str(e)}")
        return False
    finally:
        # 关闭测试服务器
        await runner.cleanup()
        logger.info("SSE测试服务器已关闭")

if __name__ == "__main__":
    # 测试SSE响应
    import asyncio
    from .zudao import create_tool as create_zudao
    
    async def run_test():
        tool = create_zudao()
        await test_sse_response(tool)
    
    asyncio.run(run_test())
