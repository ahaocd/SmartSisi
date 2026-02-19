"""
Agent模型接口 - 支持通过配置文件切换多种大模型
配置简单，只需修改system.conf中的chat_module字段
"""

import os
import time
import json
import asyncio
import traceback
import requests
import concurrent.futures
import re
from typing import Optional, Tuple, List, Dict, Any
from utils import util
# 🚨 content_db已删除，使用Mem0记忆系统
# from llm.direct_tools import process_with_tools, process_with_tools_sync, quick_tool_detection
from utils import config_util as cfg

# 添加线程池执行器，用于并行处理
_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

def process_agent_request(text, uid=0, observation="", nlp_result=None):
    """
    使用Agent处理请求
    
    Args:
        text: 用户输入文本
        uid: 用户ID
        observation: 环境观察结果
        nlp_result: NLP模型输出的结果，格式为(文本,风格)
        
    Returns:
        Tuple[str, str]: (回复文本, 风格)
    """
    try:
        # 记录start time
        start_time = time.time()
        util.log(1, f"[Agent] 开始处理Agent请求: {text}")
        
        # 使用Agent单例处理
        from llm.agent.sisi_agent import get_instance as get_agent_instance
        agent = get_agent_instance()
        
        # 设置环境观察信息
        if observation:
            agent.set_observation(observation)
            util.log(1, f"[Agent] 设置环境观察信息: {observation[:50]}...")
            
        # 调用agent处理请求，传递nlp_result
        util.log(1, f"[Agent] 传递NLP结果: {str(nlp_result)[:50]}...")
        response = agent.invoke(text, uid, nlp_result=nlp_result)
        
        # 记录处理时间
        process_time = time.time() - start_time
        util.log(1, f"[Agent] 处理完成，耗时: {process_time:.2f}秒")
        
        return response, 'gentle'
        
    except Exception as e:
        util.log(2, f"[Agent] 处理请求失败: {str(e)}")
        import traceback
        util.log(2, f"[Agent] 详细错误: {traceback.format_exc()}")
        
        # 如果处理失败但有NLP结果，返回NLP结果作为备选
        if nlp_result and isinstance(nlp_result, tuple) and len(nlp_result) >= 2:
            util.log(1, f"[Agent] 返回NLP结果作为备选方案")
            return nlp_result
        
        return f"处理请求时出错: {str(e)}", 'gentle'

def question(query_text, uid=0, observation=""):
    """处理用户问题"""
    try:
        util.log(1, f"[Agent模块] 处理请求: {query_text}...")
        
        # 确保uid是有效值
        if isinstance(uid, str):
            util.log(1, f"[Agent模块] uid为字符串'{uid}'，使用默认值0")
            uid = 0
        
        # 不再使用硬编码的工具调用检测
        # 直接交给LangChain原生的工具调用机制决定
        
        # 获取历史消息
        history_messages = get_history_messages(uid, 5)
        
        # 构建消息列表
        messages = [
            {
                "role": "system",
                "content": "你是一个智能助手，能够回答用户问题并提供实用帮助。"
            }
        ]
        
        # 添加历史消息
        if history_messages:
            messages.extend(history_messages)
            
        # 添加当前消息
        messages.append({
            "role": "user",
            "content": query_text
        })
        
        # 构建请求数据 - 为测试模式添加特殊标记
        data = build_request_data(messages, observation)
        
        # 确保测试模式下数据中包含所有必需的checkpoint参数
        is_test_mode = os.environ.get("SISI_TEST_MODE", "0") == "1"
        if is_test_mode:
            current_time = int(time.time())
            
            # 直接设置checkpoint参数到根级别，而不是嵌套在checkpoint对象中
            # 这与build_request_data函数保持一致
            thread_id = f"test_thread_{current_time}"
            checkpoint_ns = "test_namespace"
            checkpoint_id = f"test_checkpoint_{current_time}"
            
            data["thread_id"] = thread_id
            data["checkpoint_ns"] = checkpoint_ns
            data["checkpoint_id"] = checkpoint_id
                
            util.log(1, f"[Agent模块] 测试模式，确保所有checkpoint参数设置完整")
        
        # 调用模型API
        response_data = process_api_request(data)
        if not response_data:
            return {"content": "对不起，我暂时无法回答您的问题，请稍后再试。", "response_type": "text"}, "text"
        
        # 处理响应
        response = process_response(response_data)
        
        # 检查响应类型
        if isinstance(response, dict):
            # 已经是字典格式，提取必要信息
            response_type = response.get("response_type", "text")
            content = response.get("content", "")
            tool_name = response.get("tool_name", "")
            
            # 更新历史记录 - 只存储文本类型的响应
            if response_type == "text":
                try:
                    # 使用工厂方法获取content_db实例
                    db_instance = content_db.new_instance()
                    db_instance.insert_qa_pair(query_text, content, uid=uid)
                except Exception as e:
                    util.log(1, f"[Agent模块] 保存对话历史异常: {str(e)}")
            
            # 日志记录
            if response_type == "tool":
                util.log(1, f"[Agent模块] 工具调用响应: {tool_name}")
            else:
                util.log(1, f"[Agent模块] 文本响应: {str(content)[:50]}...")
            
            # 返回原始字典和响应类型
            return response, response_type
        else:
            # 兼容旧版本：如果是字符串，包装成字典格式
            content = str(response)
            util.log(1, f"[Agent模块] 文本响应(旧格式): {content[:50]}...")
            
            # 更新历史记录
            try:
                # 使用工厂方法获取content_db实例
                db_instance = content_db.new_instance()
                db_instance.insert_qa_pair(query_text, content, uid=uid)
            except Exception as e:
                util.log(1, f"[Agent模块] 保存对话历史异常: {str(e)}")
            
            # 返回结果和风格（默认gentle风格）
            return {"content": content, "response_type": "text"}, "text"
    except Exception as e:
        util.log(1, f"[Agent模块] 处理异常: {str(e)}")
        import traceback
        traceback.print_exc()
        error_msg = f"抱歉，处理您的请求时出现了错误: {str(e)}"
        return {"content": error_msg, "response_type": "error"}, "error"

def process_request_with_timeout(cont, uid=0, observation="", timeout=30.0):
    """带超时控制的请求处理"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            coro = question_async(cont, uid, observation)
            result = loop.run_until_complete(asyncio.wait_for(coro, timeout=timeout))
            return result
        finally:
            loop.close()
    except asyncio.TimeoutError:
        util.log(1, f"[Agent模块] 处理请求超时，超过{timeout}秒")
        return None
    except Exception as e:
        util.log(1, f"[Agent模块] 超时控制异常: {str(e)}")
        return None

def try_direct_tool_execution(text, uid=0):
    """尝试直接工具调用（异步）"""
    try:
        # 不再使用硬编码的工具调用检测
        # 由LangChain原生的工具调用机制决定
        
        # 如果上层已经确定需要使用工具，则直接处理
        result = process_with_tools_sync(text, uid)
        if result:
            util.log(1, f"[Agent模块] 工具处理成功: {result[:50] if isinstance(result, str) else str(result)[:50]}...")
            return result
        else:
            util.log(1, f"[Agent模块] 工具处理失败，返回None")
            return None
    except Exception as e:
        error_msg = str(e)
        util.log(2, f"[Agent模块] 工具处理异常: {error_msg}")
        return f"工具处理异常: {error_msg}"

def get_history_messages(uid=0, max_count: int = 5):
    """
    获取历史对话消息
    
    Args:
        uid: 用户ID (可能是字符串或整数)
        max_count: 最大获取消息数量
    
    Returns:
        历史消息列表
    """
    try:
        # 确保uid是整数类型
        try:
            # 如果uid是字符串（如'User'），则使用默认值0
            if isinstance(uid, str):
                util.log(1, f"[Agent模块] uid为字符串'{uid}'，使用默认值0")
                numeric_uid = 0
            else:
                numeric_uid = int(uid)
        except ValueError:
            # 转换失败时使用默认值
            util.log(1, f"[Agent模块] uid转换为整数失败，使用默认值0")
            numeric_uid = 0
        
        # 获取历史问答对
        try:
            # 使用工厂方法获取content_db实例
            db_instance = content_db.new_instance()
            history = db_instance.get_qa_pairs(uid=numeric_uid, limit=max_count*2)
        except Exception as e:
            util.log(1, f"[Agent模块] 获取历史消息异常: {str(e)}")
            history = []
            
        if not history:
            return []
            
        # 转换为消息格式
        messages = []
        for qa in history:
            # 问题
            if qa[1]:  # 确保问题不为空
                messages.append({
                    "role": "user",
                    "content": str(qa[1])  # 确保转换为字符串
                })
            
            # 回答
            if qa[2]:  # 确保回答不为空
                messages.append({
                    "role": "assistant",
                    "content": str(qa[2])  # 确保转换为字符串
                })
        
        # 取最近的几轮对话
        if len(messages) > max_count * 2:
            messages = messages[-max_count*2:]
        
        return messages
    except Exception as e:
        util.log(1, f"[Agent模块] 获取历史消息异常: {str(e)}")
        return []

def build_request_data(messages, observation="", forced_tool=None):
    """构建请求数据"""
    try:
        # 检查观察信息是否需要添加到系统提示
        if observation and messages and messages[0]["role"] == "system":
            system_content = messages[0]["content"]
            if "Current observation:" not in system_content:
                system_content += f"\n\nCurrent observation: {observation}"
                messages[0]["content"] = system_content
        
        # 构建通用请求数据
        data = {
            "messages": messages,
            "temperature": 0.2,  # 降低温度以提高工具调用的精确性
            "max_tokens": 2000,
            "stream": False,
            "extra_body": {
                "enable_thinking": True,
                "thinking_budget": 4000
            }
        }
        
        # 检查是否在测试模式下
        is_test_mode = os.environ.get("SISI_TEST_MODE", "0") == "1"
        if is_test_mode:
            # 在测试模式下添加必要的checkpoint参数
            current_time = int(time.time())
            
            # 确保checkpoint字段格式完全符合API要求
            thread_id = f"test_thread_{current_time}"
            checkpoint_ns = "test_namespace"
            checkpoint_id = f"test_checkpoint_{current_time}"
            
            # 直接设置到根级别，而不是嵌套在checkpoint对象中
            data["thread_id"] = thread_id
            data["checkpoint_ns"] = checkpoint_ns
            data["checkpoint_id"] = checkpoint_id
            
            util.log(1, f"[Agent模块] 测试模式，添加checkpoint参数: {thread_id}")
        
        # 尝试获取当前配置的模型名称
        model_name = ""
        try:
            cfg.load_config()
            model_name = cfg.key_chat_module
            
            # 不为特定模型添加不兼容的参数
        except Exception as e:
            util.log(2, f"[Agent模型] 获取模型名称异常: {str(e)}")
        
        # 分析用户最新消息内容，判断是否应该调用特定工具
        user_message = ""
        forced_tool = None
        
        # 获取最新的用户消息
        for msg in reversed(messages):
            if msg["role"] == "user":
                user_message = msg["content"].lower()
                break
        
        # 创建更全面的关键词映射来匹配工具
        tool_keyword_mapping = {
            "get_weather": [
                "天气", "气温", "下雨", "阴天", "晴天", "多云", "湿度", "温度", 
                "天气预报", "天气怎么样", "天气如何", "会下雨", "雨伞", "气象"
            ],
            "set_timer": [
                "提醒", "定时", "闹钟", "倒计时", "秒表", "计时", "分钟后", "小时后",
                "明天提醒", "设置时间", "设置闹钟", "设置提醒", "稍后提醒", "时间到"
            ],
            "get_timer": [
                "查询提醒", "查看提醒", "查询定时", "查看定时", "有什么提醒",
                "定时器列表", "闹钟列表", "查看闹钟", "我的提醒", "已设置的提醒"
            ],
            "delete_timer": [
                "删除提醒", "取消提醒", "删除定时", "取消定时", "移除提醒",
                "停止提醒", "关闭提醒", "关闭定时器", "清除提醒", "取消闹钟"
            ],
            "get_web_content": [
                "获取网页", "获取网站", "打开网页", "打开网站", "访问网页", "访问网站",
                "浏览网页", "浏览网站", "获取url", "获取链接", "打开链接", "访问链接",
                "网页内容", "网站内容", "查看网页", "网页信息", "网站信息"
            ]
        }
        
        # 检查是否应该强制使用特定工具
        for tool_name, keywords in tool_keyword_mapping.items():
            for keyword in keywords:
                if keyword in user_message:
                    forced_tool = tool_name
                    util.log(1, f"[Agent模块] 关键词'{keyword}'匹配到工具: {tool_name}")
                    break
            if forced_tool:
                break
        
        # 添加工具配置
        if cfg.agent_use_tools:
            # 定义标准工具
            standard_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "description": "获取指定城市的天气情况",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "city": {
                                    "type": "string",
                                    "description": "城市名称，如'北京'、'上海'、'深圳'等"
                                }
                            },
                            "required": ["city"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "set_timer",
                        "description": "设置定时提醒",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "time": {
                                    "type": "string", 
                                    "description": "设置时间，格式如'5分钟后'、'明天下午3点'等"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "提醒内容"
                                }
                            },
                            "required": ["time"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_timer",
                        "description": "查询当前设置的定时提醒",
                        "parameters": {
                            "type": "object",
                            "properties": {}
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "delete_timer",
                        "description": "删除指定的定时提醒",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "timer_id": {
                                    "type": "string",
                                    "description": "要删除的定时器ID"
                                }
                            },
                            "required": ["timer_id"]
                        }
                    }
                },
                {
                    "type": "function",
                    "function": {
                        "name": "get_web_content",
                        "description": "获取指定网页的内容",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "url": {
                                    "type": "string",
                                    "description": "网页地址，以http或https开头的完整URL"
                                }
                            },
                            "required": ["url"]
                        }
                    }
                }
            ]
            
            # 使用标准工具或配置中的工具
            if cfg.agent_functions and len(cfg.agent_functions) > 0:
                data["functions"] = cfg.agent_functions
            else:
                data["tools"] = standard_tools
                
            # 添加tool_choice参数，根据分析结果调整工具选择策略
            if forced_tool:
                # 强制使用特定工具
                for tool in standard_tools:
                    if tool["function"]["name"] == forced_tool:
                        data["tool_choice"] = {
                            "type": "function",
                            "function": {"name": forced_tool}
                        }
                        break
            else:
                # 自动决策是否调用工具
                data["tool_choice"] = "auto"
                
        return data
    except Exception as e:
        util.log(1, f"[Agent模块] 构建请求数据异常: {str(e)}")
        return None

def process_api_request(data):
    """发送API请求并获取响应"""
    try:
        # 根据chat_module配置选择模型
        chat_module = cfg.key_chat_module
        
        # 默认使用统一的API调用
        api_key = ""
        base_url = ""
        model_engine = ""
        
        # 根据配置文件中的chat_module决定使用哪个模型
        if chat_module == "deepseek":
            api_key = cfg.deepseek_api_key
            base_url = cfg.deepseek_base_url
            model_engine = cfg.deepseek_model_engine
            util.log(1, f"[Agent模块] 使用DEEPSEEK模型: {model_engine}")
        elif chat_module == "sisi":
            llm_cfg = cfg.get_persona_llm_config("sisi")
            api_key = llm_cfg["api_key"]
            base_url = llm_cfg["base_url"]
            model_engine = llm_cfg["model"]
            util.log(1, f"[Agent模块] 使用SISI主模型: {model_engine}")
        elif chat_module == "liuye":
            llm_cfg = cfg.get_persona_llm_config("liuye")
            api_key = llm_cfg["api_key"]
            base_url = llm_cfg["base_url"]
            model_engine = llm_cfg["model"]
            util.log(1, f"[Agent模块] 使用LIUYE模型: {model_engine}")
        else:
            # 默认使用Agent模式下的配置
            # 对于Agent模式，优先使用DeepSeek作为Agent模型
            api_key = cfg.deepseek_api_key
            base_url = cfg.deepseek_base_url
            model_engine = cfg.deepseek_model_engine
            util.log(1, f"[Agent模块] 使用DeepSeek模型: {model_engine}")
            
        # 确保API URL正确
        api_url = f"{base_url}/chat/completions"
        
        # 检查API密钥
        if not api_key:
            util.log(2, f"[Agent模块] API密钥未配置，chat_module={chat_module}")
            return None
            
        util.log(1, f"[Agent模块] 发送API请求: {api_url}")
        
        # 设置API请求头
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
        
        # 设置模型引擎
        data["model"] = model_engine
        
        # 发送请求
        response = requests.post(api_url, headers=headers, json=data, timeout=30)
        util.log(1, f"[Agent模块] API状态码: {response.status_code}")
        
        if response.status_code != 200:
            util.log(2, f"[Agent模块] API请求失败: {response.status_code} - {response.text}")
            return None
            
        return response.json()
    except Exception as e:
        util.log(1, f"[Agent模块] API请求异常: {str(e)}")
        return None

def process_response(response):
    """处理响应数据"""
    try:
        # 增加详细日志记录
        util.log(1, f"[Agent模块] 开始处理API响应...")
        
        # 提取回复内容
        if not response or "choices" not in response:
            util.log(1, f"[Agent模块] 响应无效: {str(response)[:100]}")
            return {"content": "抱歉，我没有获取到有效的回复。", "response_type": "text"}
        
        # 记录完整响应的结构
        choice_keys = response["choices"][0].keys() if response.get("choices") and len(response["choices"]) > 0 else []
        util.log(1, f"[Agent模块] 响应结构: choices[0]包含字段: {list(choice_keys)}")
            
        message = response["choices"][0]["message"]
        content = message.get("content", "")
        
        # 记录消息内容前30个字符，帮助调试
        if content is not None:
            util.log(1, f"[Agent模块] 响应内容开头: {content[:30]}")
        else:
            util.log(1, f"[Agent模块] 警告：响应内容为None")
            content = ""  # 确保content不为None
        
        # 优先检查工具调用，即使content为None
        # 先检查标准格式的工具调用
        if "tool_calls" in message and message["tool_calls"]:
            # 新格式tool_calls
            tool_calls = message.get("tool_calls", [])
            if tool_calls:
                tool_call = tool_calls[0]
                func_name = tool_call.get("function", {}).get("name", "unknown_function")
                func_args = tool_call.get("function", {}).get("arguments", "{}")
                util.log(1, f"[Agent模块] 检测到标准tool_calls格式: {func_name}")
                try:
                    # 返回结构化的字典对象，而不是JSON字符串
                    args_dict = json.loads(func_args) if isinstance(func_args, str) else func_args
                    return {
                        "content": args_dict,
                        "response_type": "tool",
                        "tool_name": func_name
                    }
                except json.JSONDecodeError as e:
                    util.log(1, f"[Agent模块] tool_calls参数解析失败: {str(e)}")
                    # 尝试修复损坏的JSON
                    if isinstance(func_args, str):
                        func_args = func_args.replace("'", '"')
                        try:
                            args_dict = json.loads(func_args)
                            return {
                                "content": args_dict,
                                "response_type": "tool",
                                "tool_name": func_name
                            }
                        except:
                            # 无法解析就返回原始文本
                            return {
                                "content": func_args,  # 返回原始参数字符串
                                "response_type": "tool",
                                "tool_name": func_name
                            }
                    else:
                        # 如果不是字符串，直接使用
                        return {
                            "content": func_args,
                            "response_type": "tool",
                            "tool_name": func_name
                        }
        
        # 检查传统的function_call格式
        if "function_call" in message:
            # 传统OpenAI格式
            func_name = message['function_call']['name']
            func_args = message['function_call']['arguments']
            util.log(1, f"[Agent模块] 检测到标准function_call格式: {func_name}")
            try:
                # 返回结构化的字典对象，而不是JSON字符串
                args_dict = json.loads(func_args) if isinstance(func_args, str) else func_args
                return {
                    "content": args_dict,
                    "response_type": "tool",
                    "tool_name": func_name
                }
            except json.JSONDecodeError as e:
                util.log(1, f"[Agent模块] function_call参数解析失败: {str(e)}")
                # 尝试修复损坏的JSON
                if isinstance(func_args, str):
                    func_args = func_args.replace("'", '"')
                    try:
                        args_dict = json.loads(func_args)
                        return {
                            "content": args_dict,
                            "response_type": "tool",
                            "tool_name": func_name
                        }
                    except:
                        # 实在无法解析就返回原始文本
                        return {
                            "content": func_args,  # 返回原始参数字符串
                            "response_type": "tool",
                            "tool_name": func_name
                        }
                else:
                    # 如果不是字符串，直接使用
                    return {
                        "content": func_args,
                        "response_type": "tool",
                        "tool_name": func_name
                    }
        
        # 尝试从文本内容中提取JSON格式的工具调用
        if content:
            # 尝试匹配完整的JSON对象
            try:
                json_pattern = r'({[\s\S]*?})'
                json_matches = re.findall(json_pattern, content)
                
                for json_str in json_matches:
                    try:
                        # 尝试解析JSON
                        json_obj = json.loads(json_str)
                        
                        # 检查是否是工具调用格式
                        if "name" in json_obj and "arguments" in json_obj:
                            # 确认是工具调用格式，返回结构化字典
                            util.log(1, f"[Agent模块] 从响应文本提取到工具调用: {json_obj['name']}")
                            args = json_obj["arguments"]
                            # 确保arguments是字典格式
                            if isinstance(args, str):
                                try:
                                    args = json.loads(args)
                                except:
                                    pass  # 如果无法解析，保持原样
                            
                            return {
                                "content": args,
                                "response_type": "tool",
                                "tool_name": json_obj["name"]
                            }
                    except json.JSONDecodeError:
                        continue
            except Exception as e:
                util.log(1, f"[Agent模块] JSON提取异常: {str(e)}")
            
            # 简化处理 - 如果没有找到有效的工具调用，直接返回内容
            util.log(1, f"[Agent模块] 未检测到工具调用，返回原始内容")
            return {
                "content": content,
                "response_type": "text"
            }
        else:
            # 内容为空但没有工具调用，返回默认消息
            return {
                "content": "抱歉，我没有获取到有效的回复。",
                "response_type": "text"
            }
    except Exception as e:
        util.log(2, f"[Agent模块] 处理响应异常: {str(e)}")
        import traceback
        util.log(2, f"[Agent模块] 异常详情: {traceback.format_exc()}")
        return {
            "content": f"处理响应时出现错误: {str(e)}",
            "response_type": "error"
        }

async def question_async(cont, uid=0, observation=""):
    """异步处理请求"""
    try:
        # 尝试直接工具调用
        tool_result = try_direct_tool_execution(cont, uid)
        if tool_result:
            return tool_result
            
        # 构建历史消息
        history_messages = get_history_messages(uid, 5)
        
        # 构建消息列表
        messages = [
            {
                "role": "system",
                "content": "你是一个智能助手，能够回答用户问题并提供实用帮助。"
            }
        ]
        
        # 添加历史消息
        if history_messages:
            messages.extend(history_messages)
            
        # 添加当前消息
        messages.append({
            "role": "user",
            "content": cont
        })
        
        # 构建请求数据
        data = build_request_data(messages, observation)
        if not data:
            return "抱歉，处理您的请求时出现了错误。", "gentle"
            
        # 确保异步函数也设置了正确的checkpoint参数
        is_test_mode = os.environ.get("SISI_TEST_MODE", "0") == "1"
        if is_test_mode:
            current_time = int(time.time())
            
            # 直接设置checkpoint参数到根级别，与其他函数保持一致
            thread_id = f"test_thread_{uid}_{current_time}"
            checkpoint_ns = "test_namespace"
            checkpoint_id = f"test_checkpoint_{current_time}"
            
            data["thread_id"] = thread_id
            data["checkpoint_ns"] = checkpoint_ns
            data["checkpoint_id"] = checkpoint_id
                
            util.log(1, f"[Agent模块异步] 测试模式，确保所有checkpoint参数设置完整")
        
        # 异步调用模型API
        loop = asyncio.get_running_loop()
        response_data = await loop.run_in_executor(_executor, lambda: process_api_request(data))
        
        if not response_data:
            return "对不起，我暂时无法回答您的问题，请稍后再试。", "gentle"
            
        # 处理响应
        response = process_response(response_data)
        
        # 更新历史记录
        try:
            # 使用工厂方法获取content_db实例
            db_instance = content_db.new_instance()
            await loop.run_in_executor(_executor, lambda: db_instance.insert_qa_pair(cont, response, uid=uid))
        except Exception as e:
            util.log(1, f"[Agent模块异步] 保存对话历史异常: {str(e)}")
        
        return response, "gentle"
    except Exception as e:
        util.log(1, f"[Agent模块异步] 处理异常: {str(e)}")
        traceback.print_exc()
        return "抱歉，处理您的请求时出现了错误。", "gentle"

# 兼容agent_coordinator的接口
def chat(text, uid=0, observation="", nlp_result=None):
    """
    处理对话请求
    
    Args:
        text: 用户输入文本
        uid: 用户ID
        observation: 观察信息，来自硬件传感器等
        nlp_result: NLP模型的处理结果
        
    Returns:
        Tuple[str, str]: (回复文本, 回复风格)
    """
    # 调用Agent模块
    return process_agent_request(text, uid, observation, nlp_result=nlp_result)

# 显式异步接口，供Agent协调器调用
async def async_question(cont, uid=0, observation=""):
    """
    明确的异步接口，用于兼容Agent协调器的异步调用
    直接调用question_async函数
    """
    return await question_async(cont, uid, observation)

# 显式异步接口，供Agent协调器调用
async def async_chat(text, uid=0, observation=""):
    """
    明确的异步接口，用于兼容agent_coordinator的异步调用
    """
    return await async_question(text, uid, observation)

# 添加mask_api_key函数定义，放在get_model_info函数之前
def mask_api_key(api_key: str) -> str:
    """
    对API密钥进行掩码处理，只显示前4位和后4位字符
    
    Args:
        api_key: 完整的API密钥
        
    Returns:
        掩码处理后的API密钥
    """
    try:
        # 参数检查
        if not api_key:
            util.log(1, f"[Agent模块] mask_api_key: API密钥为空")
            return "****"
            
        # 如果密钥长度小于8，直接返回固定掩码
        if len(api_key) < 8:
            util.log(1, f"[Agent模块] mask_api_key: API密钥长度不足，使用固定掩码")
            return "****"
        
        # 提取前4位和后4位
        prefix = api_key[:4]
        suffix = api_key[-4:]
        # 中间部分用星号替换
        masked_part = "*" * (len(api_key) - 8)
        
        # 组合最终结果
        masked_key = f"{prefix}{masked_part}{suffix}"
        util.log(1, f"[Agent模块] mask_api_key: 已成功掩码API密钥")
        
        return masked_key
    except Exception as e:
        util.log(2, f"[Agent模块] mask_api_key异常: {str(e)}")
        return "****"  # 发生异常时返回固定掩码

# 添加获取模型信息的函数，方便调试
def get_model_info():
    """获取当前使用的模型信息"""
    try:
        # 加载最新配置
        cfg.load_config()
        
        model_key = cfg.key_chat_module
        
        # 准备显示的信息
        info = {
            "module": "agent_llm",
            "model": model_key,
            "status": "ready",
            "capabilities": ["agent", "tools", "chat"]
        }
        
        # 如果有API KEY信息，添加掩码版本
        if hasattr(cfg, 'key_openai_api_key') and cfg.key_openai_api_key:
            mask_key = mask_api_key(cfg.key_openai_api_key)
            info["api_key"] = mask_key
            
        return info
    except Exception as e:
        return {
            "module": "agent_llm",
            "status": "error",
            "error": str(e)
        }

# 添加get_completion方法以兼容测试脚本
def get_completion(text, uid=0, observation=""):
    """
    获取简单文本补全，用于快速测试模型连接
    
    Args:
        text: 输入文本
        uid: 用户ID
        observation: 环境观察信息
        
    Returns:
        模型响应文本
    """
    try:
        # 构建简单消息
        messages = [
            {
                "role": "system",
                "content": "你是一个智能助手，能够回答用户问题并提供实用帮助。"
            },
            {
                "role": "user",
                "content": text
            }
        ]
        
        # 构建请求数据
        data = build_request_data(messages, observation)
        
        # 调用模型API
        response_data = process_api_request(data)
        if not response_data:
            return "模型响应为空，请检查连接和配置。"
            
        # 处理响应
        result = process_response(response_data)
        if isinstance(result, tuple):
            return result[0]  # 返回文本内容
        return result
    except Exception as e:
        util.log(2, f"[Agent模型] get_completion异常: {str(e)}")
        return f"模型调用异常: {str(e)}"

# 添加process_request方法以与agent_coordinator兼容
def process_request(text, uid=0, observation=""):
    """
    处理请求的简单包装，确保与agent协调器兼容
    
    Args:
        text (str): 用户请求文本
        uid (int, optional): 用户ID. Defaults to 0
        observation (str, optional): 观察结果. Defaults to ""
        
    Returns:
        str: 处理结果的文本内容
    """
    try:
        # 确保输入文本不为None
        if text is None:
            util.log(2, f"[Agent模块] 错误：输入文本为None")
            return "输入文本不能为None"
            
        util.log(1, f"[Agent模块] 处理请求: {text[:30]}...")
        
        # 检查是否在测试模式下
        is_test_mode = os.environ.get("SISI_TEST_MODE", "0") == "1"
        
        # 测试模式下，添加必要的checkpoint参数
        if is_test_mode:
            thread_id = f"thread_{int(time.time())}"
            util.log(1, f"[Agent模块] 测试模式，添加checkpoint参数: {thread_id}")
            
            # 确保checkpoint参数设置完整
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
            os.environ["LANGCHAIN_API_KEY"] = "ls__..."  # 实际使用时应替换为真实的API密钥
            os.environ["LANGCHAIN_PROJECT"] = "sisi-agent"
            
            util.log(1, f"[Agent模块] 测试模式，确保所有checkpoint参数设置完整")
        
        # 调用question函数处理请求
        result, result_type = question(text, uid, observation)
        
        # 返回结果 - 确保返回字符串而不是字典
        if isinstance(result, dict):
            if result_type == "tool":
                tool_name = result.get("tool_name", "未知工具")
                content = result.get("content", {})
                return f"需要使用{tool_name}工具，参数: {content}"
            else:
                # 返回文本内容
                return result.get("content", "无法处理您的请求。")
        elif isinstance(result, str):
            # 如果已经是字符串，直接返回
            return result
        else:
            # 其他类型转换为字符串
            return str(result)
    except Exception as e:
        util.log(2, f"[Agent模块] 执行异常: {str(e)}")
        import traceback
        util.log(2, f"[Agent模块] 异常详情: {traceback.format_exc()}")
        return f"处理请求时出现问题: {str(e)}"

# 快速检测是否可能需要工具调用
def is_tool_call_quick(text):
    """
    快速检测文本是否可能需要工具调用
    通过关键词匹配来判断，避免每次都调用大模型
    
    Args:
        text: 用户输入文本
        
    Returns:
        是否可能需要工具调用
    """
    # 常见工具关键词列表
    tool_keywords = [
        "天气", "weather", 
        "时间", "time", "几点", 
        "日期", "date", "几号", 
        "计算", "calculate", "compute",
        "搜索", "search", "查询", "query",
        "翻译", "translate",
        "地图", "map", "位置", "location",
        "新闻", "news",
        "股票", "stock", "股价",
        "提醒", "remind", "reminder",
        "闹钟", "alarm",
        "播放", "play", "音乐", "music",
        "打开", "open",
        "关闭", "close",
        "发送", "send", "邮件", "email",
        "消息", "message"
    ]
    
    # 检查文本中是否包含工具关键词
    text_lower = text.lower()
    for keyword in tool_keywords:
        if keyword in text_lower:
            util.log(1, f"[Agent模块] 关键词'{keyword}'匹配到工具: {text[:30]}...")
            return True
    
    return False

# 直接添加必要的简化函数到此文件
def quick_tool_detection(text: str) -> bool:
    """快速检测是否可能是工具请求(简化版，仅作兼容接口)"""
    return False

def process_with_tools(text: str, uid: int = 0) -> str:
    """使用工具处理文本请求(简化版，仅作兼容接口)"""
    return None

def process_with_tools_sync(text: str, uid: int = 0) -> str:
    """使用工具处理文本请求的同步版本(简化版，仅作兼容接口)"""
    return None

if __name__ == "__main__":
    # 简单的自测试
    print("Agent模型自测试:")
    test_query = "今天天气怎么样？"
    response, style = question(test_query)
    print(f"问题: {test_query}")
    print(f"回答: {response}")
    print(f"风格: {style}")
    print(f"当前使用模型: {get_model_info()}")

