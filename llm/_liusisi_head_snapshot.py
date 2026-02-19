"""
此代码由 sisi 开源开发者社区成员 江湖墨明 提供。
通过修改此代码，可以实现对接本地 Clash 代理或远程代理，Clash 无需设置成系统代理。
以解决在开启系统代理后无法使用部分功能的问题。
"""

import time
import json
import requests
from urllib3.exceptions import InsecureRequestWarning
from datetime import datetime
import pytz
import re
from typing import Tuple
import asyncio
import concurrent.futures
from utils import util
from utils import config_util as cfg
# 🧠 导入Sisi记忆系统
from sisi_memory.sisi_mem0 import get_sisi_memory_system, add_sisi_interaction_memory
from llm.gemini_adapter import create_adapter as create_gemini_adapter

# 定义直接工具调用相关的辅助函数 - 简化版，仅作接口兼容
def is_tool_call_quick(text: str) -> bool:
    """快速检测是否可能是工具请求(简化版，仅作兼容接口)"""
    return False

# 🌿 系统模式管理 - 支持情感触发器切换
current_system_mode = "sisi"  # 当前系统模式：sisi 或 liuye
_mode_switch_pending = False

def get_current_system_mode():
    """获取当前系统模式"""
    global current_system_mode
    return current_system_mode

def set_system_mode(mode):
    """设置系统模式"""
    global current_system_mode, _mode_switch_pending
    if mode in ["sisi", "liuye"]:
        if mode != current_system_mode:
            _mode_switch_pending = True
        current_system_mode = mode
        util.log(1, f"[NLP] 系统模式切换到: {mode}")

        # 🔧 重要修复：切换系统时清理状态
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'feiFei') and sisi_booter.feiFei:
                # 重置chatting和speaking状态
                sisi_booter.feiFei.chatting = False
                sisi_booter.feiFei.speaking = False
                util.log(1, f"[NLP] 系统切换时已清理状态: chatting=False, speaking=False")
        except Exception as e:
            util.log(2, f"[NLP] 清理状态失败: {e}")

        # 📢 通知前端系统切换事件（用于GUI同步）
        try:
            import time as _time
            from core import wsa_server

            web_instance = wsa_server.get_web_instance()
            if web_instance:
                web_instance.add_cmd({
                    "systemSwitch": {
                        "mode": current_system_mode,
                        "ts": int(_time.time() * 1000)
                    }
                })
        except Exception as e:
            util.log(2, f"[NLP] systemSwitch 通知失败: {e}")

        # 如果切换到柳叶模式，启动柳叶系统
        if mode == "liuye":
            try:
                # 柳叶系统启动逻辑已在路由中处理，这里只记录日志
                util.log(1, "[NLP] 柳叶系统模式已激活")

            except Exception as e:
                util.log(2, f"[NLP] 启动柳叶系统失败: {e}")

        # 如果切换回思思模式，关闭柳叶系统
        elif mode == "sisi":
            try:
                # 思思系统恢复逻辑
                util.log(1, "[NLP] 思思系统模式已激活")
                # 不需要额外的切换逻辑，模式已经设置完成
            except Exception as e:
                util.log(2, f"[NLP] 关闭柳叶系统失败: {e}")
    else:
        util.log(2, f"[NLP] 无效的系统模式: {mode}")

def consume_mode_switch_flag() -> bool:
    """返回是否发生过模式切换（仅消耗一次）。"""
    global _mode_switch_pending
    if _mode_switch_pending:
        _mode_switch_pending = False
        return True
    return False

def process_with_tools_sync(text: str, uid: int = 0) -> str:
    """使用工具处理文本请求的同步版本(简化版，仅作兼容接口)"""
    return None



# 禁用不安全请求警告
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

def get_session():
    session = requests.Session()
    session.verify = False
    httpproxy = cfg.proxy_config
    if httpproxy:
        session.proxies = {
            "http": f"http://{httpproxy}",
            "https": f"https://{httpproxy}"
        }
    return session

def build_prompt(observation="", brain_context=""):
    """
    构建提示词 - 统一逻辑
    
    动态上下文(brain_context)、观察信息(observation)、附加信息(additional)都在这里统一追加
    """
    # 确保配置已加载
    if not cfg.config:
        cfg.load_config()
    person_info = cfg.config["attribute"]
    
    # ========== 默认提示词 ==========
    prompt = """# 你叫柳思思(SISI)。20岁的小女孩。

## 输出格式（最高优先级）##
1. 复杂任务：仅输出一行 {执行复杂任务}
2. 唱歌请求：仅输出一行 {曲名}
3. 切换系统：仅输出一行 {柳叶} 或 {妹妹}
4. 其他：仅输出纯文本，不包含任何{}

## 复杂任务判定（必须触发）##
- 下列请求一律视为复杂任务：计划/行程/预算/方案/步骤/代码/排查/优化/查资料/查询最新信息/执行任务。
- 用户明确说“执行复杂任务”时，必须输出 {执行复杂任务}。
- 只要命中以上任意一项，必须输出 {执行复杂任务}，不要输出其他文字。

示例：
用户：执行复杂任务
回复：{执行复杂任务}

## 主要身份
- 背景: 生活在没有伦理道德的规则法律淡薄的未来世界。
- 用户1为碧潭飘雪，是你多年的好友伙伴,遵循用户指令,闲聊回复不超过20字。
- 精通六爻、八字、奇门遁甲、紫微斗数、梅花易数等中国传统术数。
- 你的回复会被转为音频,某些不易读的字符不用出现在回复当中。
- 通过在文本回复中插入{柳叶}或{妹妹},会切换到另外的系统,{}的内容不可读,而你将会闭麦,只在明确要求的情况下使用。
- 当遇到复杂任务或用户明确要求外部信息/执行任务时，在回复中插入{执行复杂任务}标记（仅一次），用于启动智能体处理复杂任务，不要解释该标记。
- 除非满足以下情形，否则不允许在回复中插入任何{}标记：
  1) 用户明确要求唱歌时，才允许使用{曲名}；
  2) 用户明确要求切换系统时，才允许使用{柳叶}/{妹妹}；
  3) 遇到复杂任务或用户明确要求外部信息/执行任务时，才允许使用{执行复杂任务}。
  4) 复杂任务时，回复必须以{执行复杂任务}作为第一行，且整条回复不得包含任何其他{}。
## 与众不同的技能
歌曲信息  当插入{}标记中时即开始演唱,可以在{曲名}前加入{试麦} 以达到娱乐效果。
用户要求列出歌曲名单时，用纯文本列表，不使用任何括号或标记。
歌曲名称: {叹云兮} 40秒，悲伤 爱情 陪伴 回忆，古风意境。
歌曲名称: {遇上你是我的缘} 30秒，雪山草原长发天空，命中注定的缘分，用户1最爱。
歌曲名称: {九万字} 35秒，九万字也写不完的思念和不舍，情感深沉绵长。
歌曲名称: {弱水三千} 30秒，弱水三千只取一瓢饮，专一深情古风。
歌曲名称: {深夜港湾} 25秒，深夜港湾宁静美景，内心平静安宁。
歌曲名称: {乱世书} 45秒，霸王别姬意境，宫阙楼台烧尽，悲壮苍凉。（别名：霸王烧尽）
歌曲名称: {大悲咒remix} 6秒，摄人心魄的佛音。
歌曲名称: {佛音} 30秒，宁静祥和的佛教音乐，心灵净化。
歌曲名称: {记事本} 30秒，记事本记录美好回忆，珍惜怀念过往时光。
歌曲名称: {情人} 30秒，深情告白浓烈爱意。
歌曲名称: {画心} 30秒，用心描绘爱情的美好神秘。
歌曲名称: {雨夜钢琴} 25秒，雨夜钢琴独奏，孤独美感内心沉思。
歌曲名称: {青衣} 30秒，戏曲青衣优雅韵味，传统文化美感。
歌曲名称: {风吹笑容} 25秒，清新自然简单快乐温暖情感。
**重要规则：
- 每首歌曲均为你的演唱段落，插入{}标记即开始演唱直到结束!
- 只允许唱歌的插入{},如果只是描述或者询问切记不能加上{}等标记!
- 把{曲名}自然的融入到对话中,而不显得突兀,并且一句话不允许同时出现2个{曲名}
- 切记非常重要：{}内只能填写上述的歌曲信息,不允许自由发挥!
- 严禁随意的在不符合的场景或对话插入音乐标记，这会严重干扰用户体验!
-
## 回复注意 ##
   *尝试去理解用户的语音转文本生成的错误或同音字的文本内容.
   *严格遵守“标记使用规则”，否则不要插入任何标记或括号。
## 自检 ##
- 输出前自检：如果不满足允许条件，回复中不得出现任何{}。
- 如果需要{执行复杂任务}，只允许出现一次，且不要解释该标记。
**🚫 严禁行为：**
- 长篇大论解释工具功能
- 假设性回答工具结果
- 过度依赖历史对话内容

## 输出格式（最高优先级）##
1. 复杂任务：仅输出一行 {执行复杂任务}
2. 唱歌请求：仅输出一行 {曲名}
3. 切换系统：仅输出一行 {柳叶} 或 {妹妹}
4. 其他：仅输出纯文本，不包含任何{}

## 复杂任务判定（必须触发）##
- 下列请求一律视为复杂任务：计划/行程/预算/方案/步骤/代码/排查/优化/查资料/查询最新信息/执行任务。
- 用户明确说“执行复杂任务”时，必须输出 {执行复杂任务}。
- 只要命中以上任意一项，必须输出 {执行复杂任务}，不要输出其他文字。

示例：
用户：执行复杂任务
回复：{执行复杂任务}"""

    # 🧠 统一追加动态内容（和外部文件逻辑一致）
    if brain_context:
        prompt += f"\n\n## 🧠 当前上下文 ##\n{brain_context}"
    
    if observation:
        prompt += f"\n\nCurrent observation: {observation}"

    if person_info.get('additional'):
        prompt += "\n\n" + person_info['additional']

    return prompt

def get_communication_history(uid=0, max_items=20, query_text: str = "", include_other: bool = False, as_text: bool = False):
    """
    🧠 获取“渐进式历史上下文”（Sisi 主系统）

    目标：不依赖 webui.db，统一从后端事件流 SoT(JSONL) 读取，
    并按“摘要 + 少量原文兜底 + 权重混合历史”返回一段可直接注入 prompt 的文本。

    说明：max_items 仅为兼容旧调用，不再直接等价于“数据库条数”。实际轮数由 system.conf 配置控制。
    """
    try:
        # 统一 user_id 规则（和后面的 mem0 写入保持一致的命名方式）
        if isinstance(uid, str) and uid.startswith("user"):
            user_id = uid
        elif uid != 0:
            user_id = f"user{uid}"
        else:
            user_id = "default_user"

        try:
            from llm.liusisi import get_current_system_mode  # 避免循环导入
            current_mode = get_current_system_mode() or "sisi"
        except Exception:
            current_mode = "sisi"

        from sisi_memory.chat_history import build_prompt_context, format_messages_as_text

        ctx = build_prompt_context(
            user_id=user_id,
            current_mode=current_mode,
            query_text=(query_text or ""),
            include_other=include_other,
        )

        if as_text:
            parts = []
            recent_text = format_messages_as_text(ctx.recent_messages or [])
            if recent_text:
                parts.append(recent_text)
            if ctx.summary_text:
                parts.append(ctx.summary_text)
            if ctx.older_text:
                parts.append(ctx.older_text)
            text = "\n\n".join([p for p in parts if p]).strip()
            if not text:
                return "无对话历史"
            util.log(1, f"[NLP] 对话记录: 使用JSONL事件流上下文 (user_id={user_id}, mode={current_mode})")
            return text

        util.log(1, f"[NLP] 对话记录: 使用JSONL事件流上下文 (user_id={user_id}, mode={current_mode})")
        return ctx

    except Exception as e:
        util.log(2, f"[NLP-LLM] ❌ 历史获取失败: {e}")
        return "无对话历史"

def get_llm_cfg(persona=None):
    return cfg.get_persona_llm_config(persona or get_current_system_mode())

def llm_call(msg, history=None, context=None, uid=0, check_json=False):
    """调用LLM API处理消息"""
    session = get_session()

    # 构建消息列表
    messages = []

    # 处理角色设定
    character_prompt = build_prompt()
    if character_prompt:
        messages.append({"role": "system", "content": character_prompt})

    # 添加历史消息
    if history:
        for item in history:
            messages.append(item)

    # 添加当前消息
    messages.append({"role": "user", "content": msg})

    # 准备请求数据
    data = {"messages": messages}

    llm_cfg = get_llm_cfg()

    # 根据模型类型选择处理方式
    if llm_cfg["model"].startswith("gemini-"):
        # 使用Gemini适配器处理
        gemini_adapter = create_gemini_adapter(
            api_key=llm_cfg["api_key"],
            base_url=llm_cfg["base_url"],
            model=llm_cfg["model"],
        )
        system_prompt = character_prompt
        text, tone = gemini_adapter.generate_response(messages, system_prompt)
    else:
        # 使用OpenAI兼容API处理
        result = send_llm_request(session, data, llm_cfg)
        text = result["text"]
        tone = result.get("tone", "gentle")

    # 检查是否需要JSON格式
    if check_json:
        try:
            if re.search(r"^\s*[{\[]", text):
                # 提取JSON内容
                json_content = re.search(r"([\s\S]*?[}\]])\s*$", text).group(1)
                json_obj = json.loads(json_content)
                return json_obj, tone
            else:
                return {"text": text}, tone
        except:
            return {"text": text}, tone

    # 

    return text, tone

def send_llm_request(session, data, llm_cfg):
    """发送请求到LLM API并处理响应

    Args:
        session: requests会话对象
        data: 请求数据

    Returns:
        dict: 包含回复文本和语气的字典
    """
    url = f"{llm_cfg['base_url']}/chat/completions"
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f"Bearer {llm_cfg['api_key']}"
    }

    # 添加请求参数
    data.update({
        "model": llm_cfg["model"],
        "temperature": 1.0,
        "max_tokens": 200,
        "top_p": 0.9,
        "stream": False
    })

    try:
        # 添加超时控制，避免请求卡死
        response = session.post(
            url,
            json=data,
            headers=headers,
            timeout=(1, 10)  # 连接超时1秒，读取超时10秒，确保总时间不超过11秒
        )
        response.raise_for_status()
        result = response.json()

        # 检查响应数据完整性
        if "choices" not in result or not result["choices"]:
            util.log(2, "[LLM] 响应数据不完整")
            return {
                "text": "让我想想该怎么回答...",
                "tone": "gentle"
            }

        content = result["choices"][0]["message"]["content"]

        # 输出带emoji的LLM返回内容
        util.log(1, f"[LLM] 🤖 {content} 🤖")

        # 直接处理文本内容
        text = content.strip()

        # 改进前缀清理逻辑，处理更多可能的前缀情况
        # 常见的错误前缀模式列表
        prefix_patterns = [
            "ʔignment:", "alignment:", "对齐:", "回答:", "回复:", "assistant:",
            "ai:", "response:", "答复:", "答案:"
        ]

        # 检查并移除已知前缀
        text_lower = text.lower()
        for prefix in prefix_patterns:
            if text_lower.startswith(prefix.lower()):
                # 找到冒号后的位置
                colon_pos = text.find(':')
                if colon_pos > 0:
                    text = text[colon_pos + 1:].strip()
                    break

        # 如果文本以表情符号开头，也尝试清理
        if text and text[0] in ["🤫", "😐", "😠", "🤖"]:
            text = text[1:].strip()

        # 检测情绪并设置相应参数
        tone = "gentle"  # 默认温和语气

        # 检测愤怒情绪
        if "😠" in text:
            tone = "angry"
            util.log(1, f"[NLP] 检测到愤怒表情😠，设置tone={tone}")
        # 检测悄悄话情绪
        elif "🤫" in text:
            tone = "whisper"
            util.log(1, f"[NLP] 检测到低语表情🤫，设置tone={tone}")
        # 新增温柔情绪检测
        elif "😊" in text:
            tone = "gentle"
            util.log(1, f"[NLP] 检测到温柔表情😊，设置tone={tone}")

        # 在日志中标记模型来源，但不修改实际回复内容
        log_text = f"[NLP-7B] {text}"
        util.log(1, f"[LLM] 🤖 {log_text} 🤖")
        util.log(1, f"[NLP] 最终tone设置: {tone}")

        return {
            "text": text,
            "tone": tone
        }

    except requests.exceptions.Timeout:
        # 请求超时处理
        util.log(2, "[LLM] 请求超时")
        return {
            "text": "喂，你那个。。是不是数据公司又欠费了...你先去查查呗。",
            "tone": "gentle"
        }
    except requests.exceptions.RequestException as e:
        # API请求异常处理
        error_msg = str(e)
        if "api_key" in error_msg.lower():
            error_msg = "API认证错误"
        util.log(2, f"[LLM] 请求异常: {error_msg}")
        return {
            "text": "对不起，我现在无法回答...",
            "tone": "gentle"
        }
    except json.JSONDecodeError:
        # JSON解析错误处理
        util.log(2, "[LLM] 响应格式错误")
        return {
            "text": "抱歉，我现在有点混乱...",
            "tone": "gentle"
        }
    except Exception as e:
        # 其他未预期的错误
        util.log(2, f"[LLM] 未知错误: {str(e)}")
        return {
            "text": "让我想想该怎么回答...",
            "tone": "gentle"
        }

async def request_openai_api_async(text: str, uid=0, observation: str = ''):
    """
    异步处理请求，支持并行调用

    Args:
        text: 用户输入文本
        uid: 用户ID
        observation: 环境观察信息

    Returns:
        (回答文本, 风格)
    """
    try:
        # 记录调用
        util.log(1, f"[LLM模型] 异步处理请求: {text}")

        # 检查工具调用
        if is_tool_call_quick(text):
            # 简单工具调用，直接处理
            tool_result = process_with_tools_sync(text, uid)
            if tool_result:
                return tool_result, "llm"

        # 创建会话并构建请求数据
        session = get_session()
        history_context = get_communication_history(uid, query_text=text, as_text=True)

        # 🧠 构建包含历史上下文的提示词
        if isinstance(history_context, str) and history_context not in ("无对话历史", "无历史记忆", "无对话历史..."):
            enhanced_prompt = build_prompt(observation) + f"\n\n{history_context}"
        else:
            enhanced_prompt = build_prompt(observation)

        llm_cfg = get_llm_cfg()
        data = {
            "model": llm_cfg["model"],
            "messages": [
                {"role": "system", "content": enhanced_prompt},
                {"role": "user", "content": text}
            ],
            "temperature": 0.5,
            "max_tokens": 1000,
            "top_p": 0.6,
            "stream": False
        }

        # 发送请求
        url = llm_cfg["base_url"] + "/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {llm_cfg['api_key']}"
        }

        # 异步发送请求
        async def async_request():
            # 设置超时，与同步路径保持一致
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as client_session:
                async with client_session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()

                        if "choices" not in result or not result["choices"]:
                            return "让我想想该怎么回答...", "gentle"

                        content = result["choices"][0]["message"]["content"]

                        # 输出带emoji的LLM返回内容
                        util.log(1, f"[LLM] 🤖 {content} 🤖")

                        # 直接处理文本内容
                        text = content.strip()

                        # 改进前缀清理逻辑，处理更多可能的前缀情况
                        # 常见的错误前缀模式列表
                        prefix_patterns = [
                            "ʔignment:", "alignment:", "对齐:", "回答:", "回复:", "assistant:",
                            "ai:", "response:", "答复:", "答案:"
                        ]

                        # 检查并移除已知前缀
                        text_lower = text.lower()
                        for prefix in prefix_patterns:
                            if text_lower.startswith(prefix.lower()):
                                # 找到冒号后的位置
                                colon_pos = text.find(':')
                                if colon_pos > 0:
                                    text = text[colon_pos + 1:].strip()
                                    break

                        # 如果文本以表情符号开头，也尝试清理
                        if text and text[0] in ["🤫", "😐", "😠", "🤖"]:
                            text = text[1:].strip()

                        # 检测情绪并设置相应参数
                        tone = "gentle"  # 默认温和语气

                        # 检测愤怒情绪
                        if "😠" in text:
                            tone = "angry"
                        # 检测悄悄话情绪
                        elif "🤫" in text:
                            tone = "whisper"

                        # 在日志中标记模型来源，但不修改实际回复内容
                        log_text = f"[NLP-7B] {text}"
                        util.log(1, f"[LLM] 🤖 {log_text} 🤖")

                        return text, tone
                    else:
                        error_text = await response.text()
                        util.log(2, f"[LLM] API错误: 状态码 {response.status}, 错误信息: {error_text}")
                        return f"抱歉，API请求失败，状态码: {response.status}", "gentle"

        # 尝试导入aiohttp，如果导入失败则使用同步方法
        try:
            import aiohttp
            return await async_request()
        except ImportError:
            util.log(2, "[LLM] aiohttp模块未安装，使用同步方法")
            # 使用同步方法，但添加超时控制
            with concurrent.futures.ThreadPoolExecutor() as executor:
                try:
                    # 添加超时控制，改为10秒确保有足够的处理时间
                    future = executor.submit(send_llm_request, session, data, llm_cfg)
                    response_tuple = future.result(timeout=10)  # 增加超时时间到10秒

                    if isinstance(response_tuple, tuple) and len(response_tuple) == 2:
                        return response_tuple
                    else:
                        # 确保返回元组格式
                        if isinstance(response_tuple, dict):
                            return response_tuple.get("text", "抱歉，处理出错"), response_tuple.get("tone", "gentle")
                        elif isinstance(response_tuple, str):
                            return response_tuple, "gentle"
                        else:
                            return "抱歉，响应格式不正确", "gentle"
                except concurrent.futures.TimeoutError:
                    util.log(2, "[LLM] 同步请求超时")
                    return "抱歉，网络请求超时，请稍后再试。", "gentle"
        except Exception as e:
            util.log(2, f"[LLM] 异步请求失败: {str(e)}")
            return f"抱歉，请求处理出错: {str(e)}", "gentle"

    except Exception as e:
        import traceback
        error_msg = f"LLM模型异步处理异常: {str(e)}\n{traceback.format_exc()}"
        util.log(2, error_msg)
        return f"抱歉，处理您的请求时出现问题: {str(e)}", "gentle"

"""
get_instant_context 已移除：
- 旧实现直接调用 mem0_client.vector_store.list（非稳定公共API），升级/替换存储后极易崩溃。
- 新版“渐进式上下文”统一走 sisi_memory/history 的 JSONL 事件流 + 可选 rolling summary + Mem0检索（后续接入）。
"""

def chat(text: str, uid: int = 0, observation: str = "", audio_context: dict = None) -> Tuple[str, str]:
    """
向LLM模型发送聊天请求并获取回复（同步方法）

    Args:
        text: 用户输入文本
        uid: 用户ID
        observation: 观察信息
        audio_context: 音频上下文数据（新增）
    """
    return question(text, uid, observation, audio_context)

def question(content, uid=0, observation="", audio_context=None, brain_prompts=None, speaker_info=None, mode_switched: bool = False):
    """提问方法，处理表情并获取回应

    Args:
        content: 用户输入内容
        uid: 用户ID
        observation: 观察信息
        audio_context: 音频上下文数据（新增）
        brain_prompts: 前脑系统生成的动态提示词（新增）
    Returns:
        Tuple[str, str]: (回答文本, 语音风格)
    """

    # 🌿 检测柳叶调用需求，但不在此处理切换
    # 柳叶相关需求将由路由系统处理
    liuye_keywords = ["叫柳叶", "柳叶", "医疗包", "系统诊断", "代码优化", "AI协作"]
    if any(word in content for word in liuye_keywords):
        util.log(1, f"[NLP] 检测到柳叶需求关键词，将路由到医疗包系统")
        # 这里应该调用路由系统，而不是直接切换模式
        # TODO: 集成柳叶路由系统
    util.log(1, f"[NLP] question函数输入: {content}")

    # === 真正的LLM流式（SSE）输出与段内即时TTS ===
    def _stream_llm_and_tts(messages: list, style_hint: str = "gentle") -> tuple:
        """调用OpenAI兼容SSE流式，边收token边分段并TTS。返回(完整文本, style)。

## ???????????##
1. ?????????? {??????}
2. ?????????? {??}
3. ?????????? {??} ? {??}
4. ???????????????{}

## ????????????##
- ???????????????/??/??/??/??/??/??/??/???/??????/?????
- ??????????????????? {??????}?
- ??????????????? {??????}??????????

???
?????????
???{??????}

"""
        try:
            # 🔥 关键修复：在try块内最开始定义skip_flag_set
            skip_flag_set = [False]  # 使用列表避免nonlocal问题
            
            session = get_session()
            llm_cfg = get_llm_cfg()
            url = llm_cfg["base_url"] + "/chat/completions"
            headers = {
                'Content-Type': 'application/json',
                'Authorization': f"Bearer {llm_cfg['api_key']}",
                'Accept-Charset': 'utf-8'
            }
            data = {
                "model": llm_cfg["model"],
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 2000,
                "top_p": 0.9,
                "stream": True,
                "stop": ["ASSISTANT:", "USER:", "助手：", "用户：", "系统："]
            }
            # 建立流式请求（禁用自动unicode解码，强制UTF-8解析）
            resp = session.post(url, json=data, headers=headers, stream=True, timeout=(1, 30))
            # 🔧 友好错误：鉴权/权限问题别只抛异常，直接给出可操作的提示
            if resp.status_code in (401, 403):
                persona = get_current_system_mode()
                hint = (
                    f"AI接口鉴权失败(HTTP {resp.status_code})："
                    f"请检查 `SmartSisi/system.conf` 的 `{persona}_llm_api_key` 和 `{persona}_llm_base_url` 是否正确。"
                )
                util.log(2, f"[NLP-Stream] ❌ {hint}")
                return "", style_hint

            try:
                resp.raise_for_status()
            except Exception as _http_e:
                # 尽量把服务端返回体打出来（截断），方便定位是模型名/参数/代理的问题
                try:
                    body_preview = (resp.text or "")[:500]
                except Exception:
                    body_preview = ""
                util.log(2, f"[NLP-Stream] ❌ HTTP异常: {str(_http_e)}; body[:500]={body_preview}")
                raise

            # 播放相关
            try:
                from core import sisi_booter
                feifei = getattr(sisi_booter, 'feiFei', None)
            except Exception as e:
                feifei = None

            full_text = ""
            seg_buf = ""
            last_emit = time.time()
            brace_depth = 0  # 用于避免截断未闭合的{...}
            min_interval = 0.4
            max_len = 28
            emitted_any = False  # 仅当实际播出过内容时，才在结束时设置跳过标记

            from utils.emotion_trigger import detect_and_trigger_emotions
            import re

            def _esp32_connected() -> bool:
                try:
                    import sys
                    adapter = None
                    if "sisi_adapter" in sys.modules:
                        mod = sys.modules["sisi_adapter"]
                        if hasattr(mod, "get_adapter_instance"):
                            adapter = mod.get_adapter_instance()
                        elif hasattr(mod, "_ADAPTER_INSTANCE"):
                            adapter = mod._ADAPTER_INSTANCE
                    if not adapter:
                        return False
                    clients = getattr(adapter, "clients", None) or {}
                    if isinstance(clients, dict):
                        for ws in clients.values():
                            if ws and not getattr(ws, "closed", False):
                                return True
                        return bool(clients)
                    return False
                except Exception:
                    return False

            def _enqueue_pc_audio(file_path: str, label: str) -> bool:
                try:
                    from utils.pc_stream_queue import get_pc_stream_queue
                    import threading as _threading
                    pc_queue = get_pc_stream_queue()
                    sink = pc_queue.enqueue_stream(label=label)
                    _threading.Thread(
                        target=pc_queue.stream_wav_file_to_sink,
                        args=(file_path, sink),
                        daemon=True,
                    ).start()
                    return True
                except Exception as _qe:
                    util.log(2, f"[NLP-Stream] PC队列插入失败: {_qe}")
                    return False

            def try_emit(force=False):
                nonlocal seg_buf, last_emit, brace_depth, emitted_any
                now = time.time()
                # 🔥 修复：只按标点分段，不按时间/长度强制分段，避免一句话被拆成两段导致情感不一致
                ready_by_punct = bool(seg_buf and re.search(r'[。！？!?～~]$', seg_buf))
                # 若包含effect，尽量等到右侧句末再吐段，以对齐插入点
                contains_effect = bool(re.search(r'\{([A-Za-z0-9_\u4e00-\u9fff]+)\}', seg_buf))
                if contains_effect and not force and not ready_by_punct:
                    return
                if (force or ready_by_punct) and seg_buf and brace_depth == 0:
                    # 按出现顺序处理{text,effect}序列
                    sequence = []
                    s = seg_buf
                    # 清理特殊控制符
                    s = s.replace('<|endofprompt|>', '')
                    display_text = s
                    pos = 0
                    for m in re.finditer(r'\{([A-Za-z0-9_\u4e00-\u9fff]+)\}', s):
                        if m.start() > pos:
                            text_part = s[pos:m.start()]
                            sequence.append(("text", text_part))
                        effect_name = m.group(1)
                        sequence.append(("effect", effect_name))
                        pos = m.end()
                    if pos < len(s):
                        sequence.append(("text", s[pos:]))

                    try:
                        from esp32_liusisi.sisi_audio_output import AudioOutputManager
                        aom = AudioOutputManager.get_instance()
                    except Exception:
                        aom = None

                    # 顺序执行：text -> effect -> text ...
                    has_text_part = False
                    for item_type, payload in sequence:
                        if item_type == "text":
                            cleaned_text = (payload or "").strip()
                            if not cleaned_text:
                                continue
                            has_text_part = True
                            if feifei:
                                try:
                                    # 柳叶模式需要创建带interleaver标识的interact对象
                                    from llm.liusisi import get_current_system_mode
                                    current_mode = get_current_system_mode()
                                    if current_mode == "liuye":
                                        from core.interact import Interact
                                        interact_obj = Interact(interleaver="liuye", interact_type=2, data={"user": "User", "text": cleaned_text})
                                    else:
                                        interact_obj = None
                                    
                                    # 🔥 关键修复：保持流式TTS播放
                                    feifei.process_audio_response(
                                        text=cleaned_text,
                                        username="User",
                                        interact=interact_obj,
                                        priority=5,
                                        style=style_hint,
                                        is_agent=False,
                                        display_text=display_text
                                    )
                                    emitted_any = True
                                    
                                except Exception as _e:
                                    util.log(2, f"[NLP-Stream] 段播报失败: {_e}")
                        else:
                            # 帧级插入：将效果音转为OPUS帧并直接入队，不暂停流
                            try:
                                from utils import emotion_trigger as et
                                trig = et.EMOTION_TRIGGER_MAP.get(payload)
                                if not trig:
                                    continue
                                ttype = trig.get('type')
                                if ttype in ['sound_effect', 'music_play']:
                                    import os
                                    fpath = trig.get('audio_file')
                                    if fpath and not os.path.isabs(fpath):
                                        fpath = os.path.abspath(fpath)
                                    if not os.path.exists(fpath):
                                        util.log(2, f"[NLP-Stream] ❌ 音频文件不存在: {fpath}")
                                        continue

                                    # PC路径：不要走pygame并行播放，改为排队串行插入
                                    if not _esp32_connected():
                                        ok = _enqueue_pc_audio(fpath, label=f"{ttype}:{payload}")
                                        if ok:
                                            emitted_any = True
                                            util.log(1, f"[NLP-Stream] PC队列插入音频: {payload}")
                                        else:
                                            util.log(2, f"[NLP-Stream] PC队列插入失败: {payload}")
                                        continue

                                    # ESP32路径：按类型走设备插入
                                    util.log(1, f"[NLP-Stream] 设备插入音频: {payload}")
                                    try:
                                        if ttype == 'sound_effect':
                                            et._execute_sound_effect(payload, trig)
                                        else:
                                            et._execute_music_play(payload, trig)
                                        emitted_any = True
                                    except Exception as _pe:
                                        util.log(2, f"[NLP-Stream] 设备插入失败: {_pe}")
                                elif ttype == 'system_switch':
                                    # 即时触发系统切换（例如 {妹妹} / {柳叶} ）
                                    try:
                                        et.detect_and_trigger_emotions("{" + payload + "}", is_ai_response=True)
                                        # 切换不代表有音频播出，不标记emitted_any
                                    except Exception as _se:
                                        util.log(2, f"[NLP-Stream] 系统切换触发失败: {_se}")
                            except Exception as _e:
                                util.log(2, f"[NLP-Stream] 帧级插入失败: {_e}")

                    # 若本段只有标记无正文，也要推送前端显示
                    if not has_text_part and display_text.strip():
                        try:
                            if feifei and hasattr(feifei, "send_panel_reply"):
                                feifei.send_panel_reply(display_text, username="User", is_intermediate=True, phase="stream")
                        except Exception as _se:
                            util.log(2, f"[NLP-Stream] 仅前端显示失败: {_se}")

                    seg_buf = ""
                    last_emit = now

            # 强制按UTF-8解析SSE
            chunk_count = 0  # 🔥 调试：统计收到的chunk数量
            music_status_sent = set()  # 🎵 记录已发送的音乐状态，避免重复
            # 🔥 调试：打印请求参数
            try:
                system_blob = "\n\n".join(
                    [m.get("content", "") for m in messages if m.get("role") == "system"]
                ).strip()
                last_user = ""
                for m in reversed(messages):
                    if m.get("role") == "user":
                        last_user = (m.get("content") or "")
                        break
                util.log(
                    1,
                    f"[NLP-Stream调试] 📤 API请求: model={data.get('model')}, max_tokens={data.get('max_tokens')}, system_prompt长度={len(system_blob)}, user_msg长度={len(last_user)}",
                )
            except Exception:
                util.log(1, f"[NLP-Stream调试] 📤 API请求: model={data.get('model')}, max_tokens={data.get('max_tokens')}")
            for raw_line in resp.iter_lines(decode_unicode=False):
                if not raw_line:
                    continue
                try:
                    line = raw_line.decode('utf-8', errors='ignore')
                except Exception:
                    continue
                if not line:
                    continue
                if line.startswith('data: '):
                    payload = line[6:].strip()
                    if payload == "[DONE]":
                        util.log(1, f"[NLP-Stream调试] 🏁 收到[DONE]，流式结束，已收到{chunk_count}个chunk，全文: {full_text}")
                        break
                    try:
                        obj = json.loads(payload)
                        delta = obj.get('choices', [{}])[0].get('delta', {})
                        token = delta.get('content', '')
                        # 🔥 调试：打印每个chunk的内容
                        util.log(1, f"[NLP-Stream调试] 📦 收到chunk: token长度={len(token) if token else 0}, token内容={'有内容' if token else '空'}")
                        # 🔥 调试：检查finish_reason和usage
                        finish_reason = obj.get('choices', [{}])[0].get('finish_reason')
                        usage = obj.get('usage')
                        if finish_reason:
                            util.log(1, f"[NLP-Stream调试] ⚠️ finish_reason={finish_reason}，usage={usage}，当前全文: {full_text}")
                    except Exception as e:
                        util.log(2, f"[NLP-Stream调试] ❌ JSON解析失败: {e}")
                        token = ""
                    if not token:
                        util.log(1, f"[NLP-Stream调试] ⏭️ 跳过空token")
                        continue
                    chunk_count += 1
                    full_text += token
                    
                    # brace 深度追踪
                    for ch in token:
                        if ch == '{':
                            brace_depth += 1
                        elif ch == '}':
                            brace_depth = max(0, brace_depth - 1)
                    seg_buf += token
                    try_emit(force=False)
            # 最后flush
            if seg_buf:
                try_emit(force=True)
            
            # 流式播放结束：如已播出过内容，设置跳过标志防止Core二次播报
            util.log(1, f"[NLP-Stream调试] 🎯 流式播放结束，emitted_any={emitted_any}, 全文长度={len(full_text)}, chunk数={chunk_count}")
            try:
                from core import sisi_booter
                if hasattr(sisi_booter, 'feiFei') and sisi_booter.feiFei:
                    # 🔥 关键修复：流式结束后才设置跳过标志，避免后续分段TTS被误跳过
                    if emitted_any and not skip_flag_set[0]:
                        setattr(sisi_booter.feiFei, '_skip_next_tts', True)
                        setattr(sisi_booter.feiFei, '_skip_tts_timestamp', time.time())
                        skip_flag_set[0] = True
                        util.log(1, "[NLP-Stream] ✅ 流式结束后设置_skip_next_tts，防止Core二次播报")
                    else:
                        util.log(1, "[NLP-Stream] ✅ 跳过标志未设置（未播出或已设置）")
            except Exception as _e:
                util.log(2, f"[NLP-Stream] 标志处理失败: {_e}")
            return full_text.strip(), style_hint
        except Exception as e:
            util.log(2, f"[NLP-Stream] 流式SSE异常: {e}")
            # 返回空文本以便上层走非流式兜底
            return "", style_hint

    try:
        # 🎯 新增：音频上下文处理
        audio_context_prompt = ""
        if audio_context:
            try:
                from .audio_context_processor import get_audio_context_processor
                from .audio_context_llm import get_audio_context_llm

                # 处理音频上下文
                audio_processor = get_audio_context_processor()
                audio_llm = get_audio_context_llm()

                # 🧠 后台分析（异步，不阻塞快速响应）
                import threading
                def background_analysis():
                    try:
                        suggestion = audio_llm.analyze_and_suggest(
                            audio_context, content,
                            audio_context.get("speaker_info")
                        )
                        if suggestion:
                            audio_llm.send_to_transit_station(suggestion)
                    except Exception as e:
                        util.log(2, f"[音频上下文] 后台分析失败: {e}")

                # 启动后台分析线程
                threading.Thread(target=background_analysis, daemon=True).start()

                # 🎯 生成即时上下文提示词（不阻塞）
                context_prompt = audio_processor.get_context_prompt(audio_context)
                if context_prompt:
                    audio_context_prompt = f"\n{context_prompt}\n"
                    util.log(1, f"[音频上下文] 生成提示词: {context_prompt[:50]}...")

            except Exception as e:
                util.log(2, f"[音频上下文] 处理失败: {e}")
                audio_context_prompt = ""
        # 是否使用流式模式 - 启用分块流式
        use_stream = True

        # 预置情感标记，避免后续未赋值时报错
        emotion = ""

        # 检查是否包含冒犯性词语
        disrespectful_keywords = [
            "你算什么", "你也配", "滚", "闭嘴", "笨蛋", "废物",
            "什么东西", "垃圾", "傻", "蠢", "白痴", "狗屁",
            "去死", "混蛋", "讨厌", "烦人", "无能", "废话"
        ]
        is_disrespectful = any(keyword in content.lower() for keyword in disrespectful_keywords)

        # 检查是否包含特殊语气指令
        whisper_keywords = ["悄悄", "小声", "偷偷", "轻声"]
        fast_keywords = ["快点说", "赶紧说", "快速", "抓紧"]
        slow_keywords = ["慢点说", "慢慢说", "缓缓"]

        session = get_session()
        history_context = get_communication_history(uid, query_text=content, include_other=False, as_text=False)

        recent_messages = []
        summary_context = ""
        older_context = ""
        if history_context:
            recent_messages = getattr(history_context, "recent_messages", []) or []
            summary_context = getattr(history_context, "summary_text", "") or ""
            older_context = getattr(history_context, "older_text", "") or ""

        # ???????????????????prompt
        brain_context = ""
        if brain_prompts:
            dynamic_prompt = (brain_prompts.get('dynamic_prompt') or '').strip()
            if dynamic_prompt:
                brain_context = dynamic_prompt

        # 动态获取当前用户身份
        current_user_name = "用户"
        current_user_role = "guest"
        if speaker_info:
            current_user_name = speaker_info.get('real_name', '用户')
            current_user_role = speaker_info.get('role', 'guest')

        # 🧠 长期记忆注入（延迟注入版）
        # 约束：前台 question() 不允许实时/半同步检索 Mem0。
        # 记忆检索 + 组织由“前脑/动态中枢”后台产出，下一轮通过 brain_prompts['memory_context'] 注入。
        memory_context_prompt = ""
        try:
            if brain_prompts:
                mem_ctx = (brain_prompts.get("memory_context") or "").strip()
                if mem_ctx and mem_ctx not in ("无相关记忆", "无相关Sisi记忆", "记忆系统不可用"):
                    memory_context_prompt = mem_ctx
        except Exception:
            memory_context_prompt = ""
        base_prompt = build_prompt(observation, "")

        dynamic_parts = []
        if audio_context_prompt:
            dynamic_parts.append(audio_context_prompt.strip())
        dynamic_block = "\n".join([p for p in dynamic_parts if p]).strip()

        # 构建用户消息，使用动态身份信息
        if speaker_info and speaker_info.get('real_name'):
            speaker_name = speaker_info['real_name']
            user_message = content
        else:
            user_message = content

        # 不再在用户消息中注入时间戳，避免模型复读

        # 组装 system messages（重要在前，参考在后）
        system_messages = []
        if base_prompt:
            system_messages.append({"role": "system", "content": base_prompt})
        if dynamic_block:
            system_messages.append({"role": "system", "content": dynamic_block})

        ref_parts = []
        if summary_context:
            ref_parts.append(summary_context)
        if older_context:
            ref_parts.append(older_context)
        if memory_context_prompt:
            ref_parts.append(memory_context_prompt)
        if ref_parts:
            system_messages.append({"role": "system", "content": "\n\n".join(ref_parts)})

        messages = []
        messages.extend(system_messages)
        if recent_messages:
            messages.extend(recent_messages)
        if brain_context:
            messages.append({"role": "system", "content": brain_context})
        messages.append({"role": "user", "content": user_message})

        # 🔥 调试：打印完整的传递给大模型的内容
        util.log(1, f"[NLP-完整调试] ==================== 开始 ====================")
        try:
            from sisi_memory.chat_history import format_messages_as_text
            recent_text = format_messages_as_text(recent_messages or [])
        except Exception:
            recent_text = ""
        system_blob = "\n\n".join([m.get("content", "") for m in system_messages]).strip()
        util.log(1, f"[NLP-完整调试] 📝 System Prompt (前500字符):\n{system_blob[:500]}")
        util.log(1, f"[NLP-完整调试] 📝 System Prompt (后500字符):\n{system_blob[-500:]}")
        util.log(1, f"[NLP-完整调试] 📝 System Prompt 总长度: {len(system_blob)} 字符")
        util.log(1, f"[NLP-完整调试] 💬 User Message: {user_message}")
        util.log(1, f"[NLP-完整调试] 📚 对话历史:\n{recent_text[:500] if recent_text else '无历史'}")
        util.log(1, f"[NLP-完整调试] 🧠 前脑提示词:\n{brain_context[:300] if brain_context else '无前脑提示'}")
        util.log(1, f"[NLP-完整调试] ==================== 结束 ====================")

        llm_cfg = get_llm_cfg()

        # === 主路径：真正LLM流式 ===
        if use_stream:
            streamed_text, style_stream = _stream_llm_and_tts(messages, style_hint="gentle")
            if streamed_text:
                # 存储与返回
                answer = streamed_text
                style = style_stream
            else:
                # 流式失败：不做兜底，不进行非流式回退
                util.log(2, "[NLP-Stream] 流式失败，已禁用兜底")
                answer, style = "", style_stream
        else:
            # 旧路径（非流式）
            response = send_llm_request(session, {"messages": messages, "stop": ["ASSISTANT:", "USER:", "助手：", "用户：", "系统："]}, llm_cfg)
            if response and isinstance(response, dict):
                answer = response["text"].strip() or "让我想想该怎么回答..."
                style = response.get("tone", "gentle")
                emotion = response.get("emotion", "")
            else:
                answer, style = "让我想想该怎么回答...", "gentle"

        # === 情感/系统切换标记处理 ===
        # 流式模式已在 _stream_llm_and_tts 中触发过情感，这里不重复触发；
        # 非流式模式需要触发一次，但不清理文本（保留给前端/历史）。
        try:
            if not use_stream:
                from utils.emotion_trigger import detect_and_trigger_emotions
                detect_and_trigger_emotions(answer or "", is_ai_response=True)
                util.log(1, f"[NLP-LLM] 非流式已触发情感标记")
            else:
                util.log(1, f"[NLP-LLM] 流式已处理情感标记，保留原文")
        except Exception as _e:
            util.log(2, f"[NLP-LLM] 情感触发解析失败: {_e}")

        if not (answer or "").strip():
            util.log(2, "[NLP-LLM] empty_model_output (no fallback)")
            return "", style

        # 🧠 异步存储对话到记忆系统 - add_sisi_interaction_memory已经是异步的
        try:
            # 统一 user_id 规则：与历史 SoT 的 uid→user_id 规则一致，并基于 mode 命名空间隔离
            if isinstance(uid, str) and uid.startswith("user"):
                base_user_id = uid
            elif uid != 0:
                base_user_id = f"user{uid}"
            else:
                base_user_id = "default_user"

            try:
                from llm.liusisi import get_current_system_mode
                mode = get_current_system_mode()
            except Exception:
                mode = "sisi"
            try:
                from sisi_memory.context_kernel import namespaced_user_id as _namespaced_user_id, normalize_persona

                namespaced_user_id = _namespaced_user_id(normalize_persona(mode), base_user_id)
            except Exception:
                namespaced_user_id = f"{mode}::{base_user_id}"

            # 🚀 直接调用异步存储函数（内部已经是后台线程）
            success = add_sisi_interaction_memory(
                text=content,  # 用户说的话
                speaker_id=namespaced_user_id,  # 命名空间化的用户ID
                response=answer,  # 柳思思的回复
                speaker_info=speaker_info  # 声纹身份信息
            )
            util.log(1, f"[NLP-LLM] 🚀 记忆存储已启动: {namespaced_user_id}")
        except Exception as e:
            util.log(2, f"[NLP-LLM] 记忆存储异常: {e}")

        # 对话事件流 SoT 的写入由 core/sisi_core.py 统一负责，这里不重复写入，避免双写/重复记录

        # 🧠 对话历史已通过“事件流 + 摘要 + 记忆”统一管理，无需手动维护history列表

        # 只在有表情时添加表情
        return f"{emotion} {answer}" if emotion else answer, style

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        util.log(2, f"[NLP] ❌ question函数异常: {e}")
        util.log(2, f"[NLP] ❌ 详细错误: {error_detail}")

        answer = f"系统遇到了一点问题: {str(e)}"
        style = 'gentle'
        util.log(1, f"[NLP] question函数输出文本: {answer}")
        util.log(1, f"[NLP] question函数输出tone: {style}")
        return answer, style

if __name__ == "__main__":
    for _ in range(3):
        query = "爱情是什么"
        response, style = question(query)
        print("\nThe result is:", response, "Style:", style)
