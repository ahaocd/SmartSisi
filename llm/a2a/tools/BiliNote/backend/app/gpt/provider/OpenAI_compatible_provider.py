import os
import httpx
from typing import Optional, Union

from openai import OpenAI

from app.utils.logger import get_logger

logging = get_logger(__name__)


def get_http_client():
    """
    获取 HTTP 客户端 - 强制绕过系统代理！
    国内大模型 API 不需要走 VPN，直连更快更稳定
    """
    # 强制不使用任何代理，绕过系统全局代理/VPN
    logging.info("🚀 直连模式（绕过系统代理）")
    return httpx.Client(
        proxy=None,  # 不使用代理
        trust_env=False,  # 关键！忽略系统环境变量中的代理设置
        timeout=httpx.Timeout(300.0, connect=30.0),  # 总超时5分钟，连接超时30秒
    )


class OpenAICompatibleProvider:
    def __init__(self, api_key: str, base_url: str, model: Union[str, None]=None):
        # 使用自定义 HTTP 客户端（支持代理配置）
        http_client = get_http_client()
        self.client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
        self.model = model

    @property
    def get_client(self):
        return self.client

    @staticmethod
    def test_connection(api_key: str, base_url: str) -> bool:
        try:
            http_client = get_http_client()
            client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
            model = client.models.list()
            logging.info("连通性测试成功")
            return True
        except Exception as e:
            logging.info(f"连通性测试失败：{e}")
            return False