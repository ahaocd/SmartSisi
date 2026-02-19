"""
Gemini模型适配器
此模块提供了与OpenAI兼容的API代理服务对接的Gemini模型支持
"""

import json
import requests
from utils import util
from utils import config_util as cfg

class GeminiAdapter:
    """Gemini模型适配器，提供与项目兼容的接口"""
    
    def __init__(self, api_key: str, base_url: str, model: str):
        """???Gemini???"""
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
    
    def create_session(self):
        """创建API请求会话"""
        session = requests.Session()
        session.verify = False
        
        # 添加代理配置
        httpproxy = cfg.proxy_config
        if httpproxy:
            session.proxies = {
                "http": f"http://{httpproxy}",
                "https": f"https://{httpproxy}"
            }
        return session
    
    def generate_response(self, messages, system_prompt=None):
        """
        使用Gemini模型生成响应
        
        Args:
            messages: 消息历史记录，格式为[{"role": "user", "content": "..."}]
            system_prompt: 系统提示，可选
            
        Returns:
            生成的响应文本和语气
        """
        session = self.create_session()
        
        # 构建Gemini格式的请求数据
        gemini_messages = []
        
        # 如果有系统提示，添加到第一条消息
        if system_prompt:
            # Gemini使用parts数组表示内容
            first_user_msg = None
            for msg in messages:
                if msg["role"] == "user":
                    first_user_msg = msg
                    break
            
            if first_user_msg:
                # 将系统提示与第一条用户消息合并
                first_user_msg["content"] = f"{system_prompt}\n\n{first_user_msg['content']}"
        
        # 转换消息格式
        current_role = None
        current_parts = []
        
        for msg in messages:
            role = msg["role"]
            content = msg["content"]
            
            if role == "user":
                if current_role == "model" and current_parts:
                    gemini_messages.append({"role": "model", "parts": current_parts})
                    current_parts = []
                
                current_role = "user"
                current_parts.append({"text": content})
            
            elif role == "assistant":
                if current_role == "user" and current_parts:
                    gemini_messages.append({"role": "user", "parts": current_parts})
                    current_parts = []
                
                current_role = "model"
                current_parts.append({"text": content})
        
        # 添加最后一组消息
        if current_parts:
            gemini_messages.append({"role": current_role, "parts": current_parts})
        
        # 构建完整请求
        request_data = {
            "contents": gemini_messages,
            "generation_config": {
                "temperature": 0.8,
                "top_p": 0.95,
                "top_k": 40,
                "max_output_tokens": 2000,
            },
            "safety_settings": [
                {
                    "category": "HARM_CATEGORY_HARASSMENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_HATE_SPEECH",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                },
                {
                    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
                    "threshold": "BLOCK_MEDIUM_AND_ABOVE"
                }
            ]
        }
        
        # 发送请求
        try:
            url = f"{self.base_url}/models/{self.model}:generateContent"
            headers = {
                'Content-Type': 'application/json',
                'x-goog-api-key': self.api_key
            }
            
            util.log(1, f"[Gemini适配器] 发送请求到: {url}")
            response = session.post(url, json=request_data, headers=headers)
            response.raise_for_status()
            result = response.json()
            
            # 输出调试信息
            util.log(1, f"[Gemini适配器] 接收到响应: {json.dumps(result, ensure_ascii=False)[:200]}...")
            
            # 解析Gemini响应
            if "candidates" in result and result["candidates"]:
                candidate = result["candidates"][0]
                if "content" in candidate and candidate["content"]["parts"]:
                    content = candidate["content"]["parts"][0]["text"]
                    
                    # 输出带emoji的LLM返回内容
                    util.log(1, f"[Gemini] 🤖 {content} 🤖")
                    
                    # 处理文本内容
                    text = content.strip()
                    
                    # 检测情绪并设置相应参数
                    tone = "gentle"  # 默认温和语气
                    
                    # 检测愤怒情绪
                    if "😠" in text:
                        tone = "angry"
                    # 检测悄悄话情绪
                    elif "🤫" in text:
                        tone = "gentle"
                    
                    return text, tone
            
            return "让我想想该怎么回答...", "gentle"
                
        except requests.exceptions.RequestException as e:
            util.log(2, f"[Gemini适配器] API请求失败: {str(e)}")
            
            if hasattr(e, 'response') and e.response:
                try:
                    error_detail = e.response.json()
                    util.log(2, f"[Gemini适配器] 返回错误详情: {str(error_detail)}")
                except:
                    util.log(2, f"[Gemini适配器] 返回状态码: {e.response.status_code}, 内容: {e.response.text[:200]}")
            
            return f"抱歉，网络请求出现问题，请稍后再试。(错误: {str(e)[:50]}...)", "gentle"
        except Exception as e:
            util.log(2, f"[Gemini适配器] 处理异常: {str(e)}")
            return f"抱歉，处理您的请求时出现问题。(错误: {str(e)[:50]}...)", "gentle"

# 创建单例实例
def create_adapter(api_key: str, base_url: str, model: str) -> GeminiAdapter:
    return GeminiAdapter(api_key=api_key, base_url=base_url, model=model)
