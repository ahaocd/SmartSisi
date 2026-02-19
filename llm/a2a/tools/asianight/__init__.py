"""
ASIANIGHT内容自动化智能体

功能：
- Telegram群组数据采集
- AI去水印
- 视频AI洗稿
- 自动发布到网站
"""

from .asianight_agent_tool import (
    AsianightAgent,
    TelegramMediaScraper,
    VideoToArticleConverter,
    WatermarkRemover,
    a2a_tool_asianight_agent
)

__version__ = "1.0.0"
__all__ = [
    'AsianightAgent',
    'TelegramMediaScraper',
    'VideoToArticleConverter',
    'WatermarkRemover',
    'a2a_tool_asianight_agent'
]



