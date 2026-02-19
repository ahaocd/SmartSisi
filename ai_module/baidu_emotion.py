import os
import sys
import json
import requests
import time

# 添加项目根目录到Python路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from utils import util, config_util as cfg

# 确保配置文件已加载
cfg.load_config()

class BaiduEmotion:
    def __init__(self):
        self.app_id = cfg.baidu_dialogue_emotion_app_id
        self.api_key = cfg.baidu_dialogue_emotion_api_key
        self.secret_key = cfg.baidu_dialogue_emotion_secret_key
        self._access_token = None
        self._token_expire_time = 0
        self._cache = {}  # 添加缓存
        self._cache_expire = 300  # 缓存有效期（秒）
        util.log(1, f"初始化百度情绪识别: app_id={self.app_id}, api_key={self.api_key}")

    def _get_from_cache(self, text):
        """从缓存中获取结果"""
        if text in self._cache:
            result, timestamp = self._cache[text]
            if time.time() - timestamp < self._cache_expire:
                return result
            else:
                del self._cache[text]
        return None

    def _add_to_cache(self, text, result):
        """添加结果到缓存"""
        self._cache[text] = (result, time.time())
        # 清理过期缓存
        current_time = time.time()
        self._cache = {k: v for k, v in self._cache.items() 
                      if current_time - v[1] < self._cache_expire}

    def get_access_token(self):
        """获取百度AI平台的access token"""
        # 如果token未过期，直接返回
        if self._access_token and time.time() < self._token_expire_time:
            util.log(1, "使用缓存的access token")
            return self._access_token

        url = "https://aip.baidubce.com/oauth/2.0/token"
        params = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.secret_key
        }
        
        try:
            util.log(1, f"请求access token: {url}")
            util.log(1, f"参数: {params}")
            response = requests.post(url, params=params)
            util.log(1, f"响应状态码: {response.status_code}")
            util.log(1, f"响应内容: {response.text}")
            
            if response.status_code == 200:
                result = response.json()
                self._access_token = result.get("access_token")
                # token有效期30天，这里设置29天后过期
                self._token_expire_time = time.time() + 29 * 24 * 3600
                util.log(1, f"获取到新的access token: {self._access_token}")
                return self._access_token
            else:
                util.log(1, f"[x] 获取百度access_token失败: {response.text}")
                return None
        except Exception as e:
            util.log(1, f"[x] 获取百度access_token异常: {str(e)}")
            return None

    def get_dialogue_sentiment(self, text):
        """
        获取对话文本的情绪
        :param text: 对话文本
        :return: 情绪类型
        """
        token = self.get_access_token()
        if not token:
            return "neutral"

        url = f"https://aip.baidubce.com/rpc/2.0/nlp/v1/emotion?access_token={token}"
        
        payload = {
            "text": text.strip(),
            "scene": "default"
        }
        
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        
        try:
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code == 200:
                result = response.json()
                if "items" in result:
                    items = result["items"]
                    # 简单获取概率最高的情绪
                    max_prob_emotion = max(items, key=lambda x: x["prob"])
                    emotion_type = max_prob_emotion["label"]
                    
                    # 基础情感映射
                    emotion_mapping = {
                        "angry": "angry",
                        "fear": "fearful",
                        "sad": "sad",
                        "disgust": "disgusting",
                        "happy": "happy",
                        "gratitude": "thankful",
                        "like": "like",
                        "optimistic": "happy",
                        "pessimistic": "sad",
                        "neutral": "neutral"
                    }
                    
                    return emotion_mapping.get(emotion_type, "neutral")
            
            return "neutral"
        except Exception as e:
            util.log(1, f"[x] 情绪识别异常: {str(e)}")
            return "neutral"

# 全局实例
_emotion_instance = None

def get_dialogue_sentiment(text):
    """
    获取对话文本的情绪（全局函数）
    :param text: 对话文本
    :return: 情绪类型
    """
    global _emotion_instance
    if _emotion_instance is None:
        _emotion_instance = BaiduEmotion()
    return _emotion_instance.get_dialogue_sentiment(text)

if __name__ == "__main__":
    # 测试代码
    test_text = "今天真是太开心了！"
    util.log(1, f"测试文本: {test_text}")
    emotion = get_dialogue_sentiment(test_text)
    util.log(1, f"识别结果: {emotion}")

