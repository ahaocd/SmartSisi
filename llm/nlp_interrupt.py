#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
智能打断专用大模型 - 基于GPT-4.1-nano
专门负责打断决策的LLM模块
"""

import json
import requests
from utils import util
from utils import config_util as cfg

def question(prompt, uid=0):
    """
    智能打断决策接口
    
    Args:
        prompt (str): 打断决策prompt
        uid (int): 用户ID
        
    Returns:
        str: 大模型返回的JSON决策结果
    """
    interrupt_model = InterruptModel()
    answer = interrupt_model.question(prompt, uid)
    return answer

class InterruptModel:
    """智能打断专用大模型"""

    def __init__(self):
        # 从system.conf读取打断模型配置
        try:
            cfg.load_config()  # 确保配置已加载

            # 使用全局变量方式读取配置
            self.api_key = getattr(cfg, 'interrupt_model_api_key', '')
            self.model = getattr(cfg, 'interrupt_model_engine', '')
            self.base_url = getattr(cfg, 'interrupt_model_base_url', '')
            self.max_tokens = int(getattr(cfg, 'interrupt_model_max_tokens', '500'))
            self.temperature = float(getattr(cfg, 'interrupt_model_temperature', '0.3'))
            self.enabled = getattr(cfg, 'interrupt_model_enabled', 'true').lower() == 'true'

            # 检查必需配置
            if not self.api_key or not self.model or not self.base_url:
                util.log(2, f"[打断模型] 配置不完整 - API Key: {'已设置' if self.api_key else '未设置'}, 模型: {self.model or '未设置'}, URL: {self.base_url or '未设置'}")
                self.enabled = False

            util.log(1, f"[打断模型] 初始化完成 - 模型: {self.model}, 基础URL: {self.base_url}, 启用: {self.enabled}")

        except Exception as e:
            util.log(2, f"[打断模型] 配置读取失败: {str(e)}")
            # 配置读取失败时禁用
            self.api_key = ''
            self.model = ''
            self.base_url = ''
            self.max_tokens = 500
            self.temperature = 0.3
            self.enabled = False

    def question(self, prompt, uid=0):
        """
        调用打断决策模型

        Args:
            prompt (str): 打断决策prompt
            uid (int): 用户ID

        Returns:
            str: 模型返回的JSON决策结果
        """
        try:
            # 检查是否启用
            if not self.enabled:
                util.log(1, f"[打断模型] 模型未启用，返回默认决策")
                return self._get_default_decision("disabled")

            util.log(1, f"[打断模型] 开始决策，用户ID: {uid}")

            # 构造请求
            url = f"{self.base_url}/chat/completions"
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            
            # 🔧 关键修复：不需要system_prompt，直接使用smart_interrupt.py传来的完整prompt

            # 🔧 关键修复：直接使用smart_interrupt.py传来的完整prompt，不添加system_prompt
            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "user",
                        "content": prompt  # 🔧 直接使用smart_interrupt构建的完整prompt
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
                "stream": False,
                "enable_thinking": False  # 🔧 修复：qwen3-8b非流式调用必须设置为False
            }
            
            # 发送请求
            util.log(1, f"[打断模型] 发送请求到: {url}")
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            
            if response.status_code != 200:
                util.log(2, f"[打断模型] API请求失败: {response.status_code} - {response.text}")
                return self._get_default_decision("api_error")
            
            # 解析响应
            response_data = response.json()
            
            if 'choices' not in response_data or not response_data['choices']:
                util.log(2, f"[打断模型] 响应格式错误: {response_data}")
                return self._get_default_decision("response_error")
            
            answer = response_data['choices'][0]['message']['content'].strip()
            util.log(1, f"[打断模型] 模型返回: {answer[:100]}...")
            
            # 🔧 修复：清理markdown代码块标记并验证JSON格式
            try:
                # 清理可能的markdown代码块标记
                cleaned_answer = answer.strip()
                if cleaned_answer.startswith('```json'):
                    cleaned_answer = cleaned_answer[7:]  # 移除 ```json
                if cleaned_answer.endswith('```'):
                    cleaned_answer = cleaned_answer[:-3]  # 移除 ```
                cleaned_answer = cleaned_answer.strip()

                # 验证清理后的JSON
                json.loads(cleaned_answer)
                util.log(1, f"[打断模型] JSON解析成功: {cleaned_answer[:100]}...")
                return cleaned_answer
            except json.JSONDecodeError:
                util.log(2, f"[打断模型] 返回的不是有效JSON: {answer}")
                return self._get_default_decision("json_error")
                
        except requests.exceptions.Timeout:
            util.log(2, f"[打断模型] 请求超时")
            return self._get_default_decision("timeout")
        except Exception as e:
            util.log(2, f"[打断模型] 请求异常: {str(e)}")
            return self._get_default_decision("exception")

    def _get_default_decision(self, error_type):
        """
        获取默认决策（当模型调用失败时）

        Args:
            error_type (str): 错误类型

        Returns:
            str: 默认决策JSON
        """
        # 🔧 简化：根据错误类型返回默认决策
        if error_type == "disabled":
            reason = "打断模型未启用"
            error_response = "系统没启动"
        elif error_type == "api_error":
            reason = "API调用失败"
            error_response = "网络抽风了"
        elif error_type == "timeout":
            reason = "请求超时"
            error_response = "网络太慢了"
        else:
            reason = f"模型错误: {error_type}"
            error_response = "出问题了"

        default_decision = {
            "should_interrupt": False,
            "response_text": error_response,  # 🔧 修复：错误时也要说话，保持柳思思个性
            "function_to_call": None,
            "restart_full_flow": False,
            "priority": "medium",  # 🔧 提高优先级，确保错误信息能被听到
            "reason": reason,
            "is_meaningless": False
        }

        return json.dumps(default_decision, ensure_ascii=False)

    def test_connection(self):
        """
        测试模型连接
        
        Returns:
            bool: 连接是否成功
        """
        try:
            test_prompt = "测试连接"
            
            result = self.question(test_prompt, 0)
            
            # 尝试解析返回结果
            json.loads(result)
            util.log(1, f"[打断模型] 连接测试成功")
            return True
            
        except Exception as e:
            util.log(2, f"[打断模型] 连接测试失败: {str(e)}")
            return False

# 全局实例
_interrupt_model_instance = None

def get_interrupt_model():
    """获取打断模型实例"""
    global _interrupt_model_instance
    if _interrupt_model_instance is None:
        _interrupt_model_instance = InterruptModel()
    return _interrupt_model_instance

# 兼容性接口
def interrupt_decision(prompt, uid=0):
    """
    打断决策接口（兼容性）

    Args:
        prompt (str): 决策prompt
        uid (int): 用户ID

    Returns:
        dict: 解析后的决策结果
    """
    try:
        result = question(prompt, uid)
        return json.loads(result)
    except Exception as e:
        util.log(2, f"[打断模型] 决策解析失败: {str(e)}")
        # 🔧 简化：解析失败时的默认回复
        return {
            "should_interrupt": False,
            "response_text": "解析出错了",
            "function_to_call": None,
            "restart_full_flow": False,
            "priority": "medium",
            "reason": "parse_error",
            "is_meaningless": False
        }




