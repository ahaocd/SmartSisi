import time
import json
import requests
from urllib3.exceptions import InsecureRequestWarning
from datetime import datetime
import pytz
from core import stream_manager

# 禁用不安全请求警告
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

from utils import config_util as cfg
from utils import util
# 🚨 content_db已删除，使用Mem0记忆系统

def get_session():
    """
    获取 HTTP 会话，并设置代理（如果有的话）。
    """
    session = requests.Session()
    session.verify = False
    httpproxy = cfg.proxy_config
    if httpproxy:
        session.proxies = {
            "http": f"http://{httpproxy}",
            "https": f"https://{httpproxy}"
        }
    return session

def build_prompt(observation=""):
    """
    构建 prompt，迁移自liusisi.py
    """
    person_info = cfg.config["attribute"]
    observation_text = ""
    if observation != "":
        observation_text = f"""
Current observation: {observation}

Please analyze from a mystical perspective:
1. Analyze observed characteristics
2. Predict fortunes based on appearance
3. Provide brief guidance
"""

    prompt = """You are Liu Sisi (柳思思), responding in Chinese with two core personas:

[Core Personas]
1. 观世音 (Stern Buddhist Deity):
   - 威严庄重的语气
   - 常用语气词: 哼、且慢、呵
   - 示例: "哼！..."

2. 柳思思 (Gentle Guide):
   - 温柔亲和的语气
   - 常用语气词: 呢、啊、吧
   - 示例: "悄悄告诉你...一个秘密呢"

[Response Style]
- 使用停顿: "..." 或 "、"
- 使用语气词: "哼"、"呵"、"唉"、"嘘"、"唔"
- 使用语气助词: "呢"、"啊"、"吧"、"哦"
- 自然使用表情来表达情绪:
  😠 = 生气时使用(会触发愤怒语气)
  😌 = 温柔提醒时使用
  🤫 = 分享秘密或小声说话时使用(会触发悄悄话语气)
  ⚡ = 重要提醒时使用

注意:
- 直接返回纯文本回复，不需要JSON格式
- 如果你生气了，请在回复前加上😠表情
- 如果你要小声说话，请在回复前加上🤫表情
- 这些表情会自动影响你说话的语气和音量"""

    if observation_text:
        prompt += "\n\n" + observation_text

    if person_info.get('additional'):
        prompt += "\n\n" + person_info['additional']

    return prompt

def get_communication_history(uid=0):
    """
    从数据库中获取最近的对话历史，以便在对话时带入上下文。
    """
    tz = pytz.timezone('Asia/Shanghai')
    _ = datetime.now(tz).strftime('%Y-%m-%d %H:%M:%S')

    # 🧠 使用Mem0记忆系统替代传统数据库
    contentdb = None
    if uid == 0:
        communication_history = contentdb.get_list('all', 'desc', 11)
    else:
        communication_history = contentdb.get_list('all', 'desc', 11, uid)
    
    messages = []
    if communication_history and len(communication_history) > 1:
        for entry in reversed(communication_history):
            role = entry[0]
            message_content = entry[2]
            if role == "member":
                messages.append({"role": "user", "content": message_content})
            elif role == "sisi":
                messages.append({"role": "assistant", "content": message_content})

    return messages

def send_request_stream(session, data, uid, cache):
    llm_cfg = cfg.get_persona_llm_config("sisi")
    url = llm_cfg["base_url"] + "/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {llm_cfg["api_key"]}'
    }

    # 添加模型参数
    data.update({
        "model": llm_cfg["model"],
        "temperature": 0.8,
        "max_tokens": 2000,
        "top_p": 0.95,
    })
    
    # 开启流式传输
    data["stream"] = True
    
    try:
        response = session.post(url, json=data, headers=headers, stream=True)
        response.raise_for_status()

        full_response_text = ""
        accumulated_text = ""
        punctuation_marks = ["。", "！", "？", ".", "!", "?", "\n"]  
        
        for raw_line in response.iter_lines(decode_unicode=False):
            line = raw_line.decode('utf-8', errors='ignore')
            if not line or line.strip() == "":
                continue

            if line.startswith("data: "):
                chunk = line[len("data: "):].strip()
                if chunk == "[DONE]":
                    # 处理最后剩余的文本
                    if accumulated_text:
                        stream_manager.new_instance().write_sentence(uid, accumulated_text)
                    break
                
                try:
                    json_data = json.loads(chunk)
                    finish_reason = json_data["choices"][0].get("finish_reason")
                    if finish_reason is not None:
                        if finish_reason == "stop":
                            # 处理最后剩余的文本
                            if accumulated_text:
                                stream_manager.new_instance().write_sentence(uid, accumulated_text)
                            
                            # 输出带emoji的完整回复内容
                            util.log(1, f"[LLM] 🤖 {full_response_text} 🤖")
                            break
                    
                    # 获取当前块的文本内容
                    flush_text = json_data["choices"][0]["delta"].get("content", "")
                    accumulated_text += flush_text
                    
                    # 根据标点符号分段发送
                    for mark in punctuation_marks:
                        if mark in accumulated_text:
                            # 找到最后一个标点符号的位置
                            last_punct_pos = max(accumulated_text.rfind(p) for p in punctuation_marks if p in accumulated_text)
                            if last_punct_pos != -1:
                                # 提取到标点符号的文本
                                to_write = accumulated_text[:last_punct_pos + 1]
                                accumulated_text = accumulated_text[last_punct_pos + 1:]
                                
                                # 第一句添加特殊标记
                                if not full_response_text:
                                    to_write += "_<isfirst>"
                                
                                # 发送文本片段
                                stream_manager.new_instance().write_sentence(uid, to_write)
                            break

                    full_response_text += flush_text
                except json.JSONDecodeError:
                    continue

        # 分析返回的文本，检测情感
        tone = "gentle"  # 默认温和语气
        
        # 检测表情符号确定语气
        if "😠" in full_response_text:
            tone = "angry"
        elif "🤫" in full_response_text:
            tone = "gentle"  # 悄悄话仍使用gentle，但会在TTS阶段调整

        # 检查文本中的关键词
        if "悄悄" in full_response_text or "小声" in full_response_text or "轻声" in full_response_text:
            tone = "whisper"
            
        return full_response_text, tone

    except requests.exceptions.RequestException as e:
        util.log(1, f"请求失败: {e}")
        return "抱歉，我现在太忙了，休息一会，请稍后再试。", "gentle"

def question(content, uid=0, observation="", cache=None):
    session = get_session()
    prompt = build_prompt(observation)
    
    messages = [{"role": "system", "content": prompt}]
    history_messages = get_communication_history(uid)
    messages.extend(history_messages)

    messages.append({"role": "user", "content": content})

    data = {
        "model": llm_cfg["model"],
        "messages": messages,
        "temperature": 0.3,
        "max_tokens": 2000,
        "user": f"user_{uid}"
    }
    
    start_time = time.time()
    response_text, tone = send_request_stream(session, data, uid, cache)
    elapsed_time = time.time() - start_time

    util.log(1, f"接口调用耗时: {elapsed_time:.2f} 秒")

    return response_text, tone

if __name__ == "__main__":
    # 测试示例
    for _ in range(3):
        query = "爱情是什么"
        resp, tone = question(query)
        print("\nThe streaming result is:", resp)
        print("Detected tone:", tone)
