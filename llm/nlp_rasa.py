"""
中转站优化处理 - 负责优化中转站关键信息并传递到SmartSisi核心
"""
import json
import requests
import logging
import traceback
import os
import sys  # 添加sys模块导入
import time
import random
import re

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 导入项目模块
from utils import util

# 统一的词汇列表 - 全局定义避免重复
# 第一阶段词汇列表 - 所有工具通用
FIRST_PHASE_PHRASES = [
    "哦...", "那...", "知道了...", "明白啦...", "行..吧...",
    "嗯...嗯...", "啊...", "嘿嘿...",
    "嘻嘻...", "唔...", "啦啦啦...", "好...吧...", "行了...行了..."
]

# 第一阶段备选短语（超过限制时使用）- 所有工具通用
FIRST_PHASE_FALLBACK = [
    "行吧", "我看一下", "好吧我弄下", "额，好嘛", "哦！知道了！",
    "嘿嘿，哦", "切~", "哼~", "唔...", "等下啊", "让我康康", "哎呀好吧"
]

# 第二阶段词汇列表 - 所有工具通用
SECOND_PHASE_PHRASES = [
    "等我一下下", "找找看咯", "我在忙呢", "就好啦~", "转啊转~", "等等哈",
    "快出来了", "别急嘛", "看我速度", "嘿嘿在查", "别催啦"
]

# 统一优化提示词模板
UNIFIED_TEMPLATE = """可以考虑记忆和历史上下文。
{content}
"""

def format_history(history_records):
    """格式化历史对话记录为文本格式"""
    if not history_records:
        return "无历史对话"

    formatted = []
    for record in history_records:
        role = "用户" if record[0] != "sisi" else "助手"
        content = record[2]
        formatted.append(f"{role}: {content}")

    return "\n".join(formatted)

def call_optimize_api(prompt, content, model, username="User", phase=None, prev_optimized=None):
    """调用优化API - 统一处理所有工具类型，使用全局词汇列表"""
    from utils import config_util

    # 确保配置已加载
    config_util.load_config()

    api_url = config_util.llm_optimize_url
    api_key = config_util.llm_optimize_key

    # 增加日志记录
    util.log(1, f"[NLP] 开始调用优化API: URL={api_url}, 模型={model}")
    util.log(1, f"[NLP] 源内容长度: {len(content)} 字符")

    # 🧠 使用Sisi记忆系统获取上下文
    history_records = []
    try:
        from sisi_memory.sisi_mem0 import get_sisi_memory_context

        # 🔥 简单处理：用户名就是说话的人
        speaker_id = f"user_{username}" if username else "default_user"

        # 🧠 获取最近对话上下文
        memory_context = get_sisi_memory_context("最近对话", speaker_id)

        # 🚀 简单处理：直接使用上下文
        if memory_context and memory_context != "无相关Sisi记忆":
            timestamp = int(time.time())
            history_records.append(("context", "memory", memory_context[:200], timestamp, speaker_id, 1))
            util.log(1, f"[NLP-RASA] 🧠 获取记忆上下文: {speaker_id} - {len(memory_context)}字符")
        else:
            util.log(1, f"[NLP-RASA] 🧠 无相关记忆上下文: {speaker_id}")
    except Exception as e:
        util.log(2, f"[NLP] 快速上下文获取失败: {e}")
        import traceback
        util.log(2, f"[NLP] 错误详情: {traceback.format_exc()}")
        history_records = []

    # 🔧 修复：寻找NLP快速回复和打断模型回复
    nlp_response = None
    interrupt_response = None

    for record in history_records:
        if record[0] == "sisi":
            # 🔧 简化：只检查优先级7的高优先级回复（就是打断回复）
            record_content = str(record[2]) if len(record) > 2 else ""
            record_source = str(record[1]) if len(record) > 1 else ""

            # 检查是否是优先级7的打断回复
            if "7" in record_source and not interrupt_response:
                interrupt_response = record_content
                util.log(1, f"[NLP] 检测到打断回复: {record_content}")
            # 检查是否是NLP快速回复
            elif "agent" not in record_source.lower() and not nlp_response:
                nlp_response = record_content

    # 简化内容处理
    short_content = content[:500] + ("..." if len(content) > 500 else "")

    # 🔥 修复：如果prompt为None，使用内部完整角色定义，否则使用传入的prompt
    if prompt is None:
        # 根据不同阶段构建不同的提示词（使用内部完整角色定义）
        if phase == "start":
            # 第一阶段只需要选择固定过渡词 - 统一所有工具类型
            enhanced_prompt = f"""
你是柳思思。任务：生成一个非常短的开场词(最多8个字)。

【场景说明】
用户刚刚问了一个问题，需要你查询信息。这是一段持续约40秒的过程的开始阶段。
你需要表达"刚听到问题，开始思考"的状态。

【历史对话】
用户问题: {short_content}
你已经回复过的上一句话是: "{nlp_response}"
{f'你刚刚说了: "{interrupt_response}"' if interrupt_response else ''}

【时间感知】
- 0秒：现在需要说第一句话（开始思考）
- 15秒：稍后会说第二句话（正在查询）
- 40秒：最后会说第三句话（得到结果）

【回复要求】
1. 只生成一个8字以内的简短回应，表达"开始思考"的状态
2. 从以下选项中选择一个词以表达初始反应
   {"、".join(FIRST_PHASE_PHRASES)}
3. 必须极短，不超过8个字

以JSON格式返回，包含一个"response"字段，值必须是上述选项之一，格式：{{"response": "选项"}}
"""

        elif phase == "middle":
            # 第二阶段 - 统一所有工具类型使用相同词汇列表
            first_response = prev_optimized.get('start', '') if prev_optimized else ''

            enhanced_prompt = f"""
你是柳思思。任务：生成一个非常短的过渡句(最多8个字)。

【场景说明】
这是一段约40秒查询过程的中间阶段(约15秒处)，你已经开始查询但还没有结果。
你的第一句话(0秒时)是: "{first_response}"
现在需要表达"正在查询/等待中"的状态。

【历史对话】
用户问题: {short_content}
你已经回复过的上一句话是: "{nlp_response}"
{f'你刚刚说了: "{interrupt_response}"' if interrupt_response else ''}

【时间感知】
- 0秒：你说了"{first_response}"（开始思考）
- 15秒：现在需要说第二句话（正在查询）
- 40秒：稍后会说第三句话（得到结果）

【回复要求】
1. 只生成一个8字以内的简短回应，表达"正在查询/等待"的状态
2. 从以下选项中选择一个词以表达等待感
   {"、".join(SECOND_PHASE_PHRASES)}
3. 必须极短，不超过8个字
4. 要与你的第一句话形成自然的连续感，体现时间推进

以JSON格式返回，包含一个"response"字段，格式：{{"response": "选项"}}
"""

        elif phase == "final":
            # 最终阶段，获取前两个阶段的实际回复，不使用硬编码默认值
            has_previous_responses = False
            first_response = ""
            middle_response = ""

            if prev_optimized and 'start' in prev_optimized and prev_optimized['start']:
                first_response = prev_optimized['start']
                has_previous_responses = True

            if prev_optimized and 'middle' in prev_optimized and prev_optimized['middle']:
                middle_response = prev_optimized['middle']
                has_previous_responses = True

            # 构建工具结果的提示信息 - 统一处理所有工具类型
            tool_specific_info = "搜索结果、名称、时间、地址、价格等关键信息"

            # 根据是否有前面的回复决定提示词
            if has_previous_responses:
                # 有前面的回复
                enhanced_prompt = f"""
你是柳思思，20岁小女孩。性格傲娇、叛逆，喜欢性挑逗，个性天真但充满好奇。

【思考过程说明】
这是一次持续约40秒的查询过程，模拟真实人类思考信息检索过程：
- 开始阶段(0秒)你说: "{first_response}" - 表达初始思考状态
- 中间阶段(15秒)你说: "{middle_response}" - 表达等待或搜索中的状态
- 现在(40秒)你需要生成获得结果后的回应

【关键理解】
整个过程应模拟人类获取信息的自然思考流程：从好奇→搜索→发现的完整心理变化。

【工具返回的最终结果】
{content[:2000]}

【对话历史】
用户问题: {short_content}
你之前的回复: "{nlp_response}"
{f'你刚刚说了: "{interrupt_response}"' if interrupt_response else ''}



【任务】
生成查询结果后的回应，必须:
生成查询结果后的第三句话，必须:
1. 表现出思考过程的自然进展，如从"不确定"到"寻找"再到"得到答案"的心理变化
2. 包含工具结果的关键信息({tool_specific_info})，但要用自然语言表达
3. 让整个三句话听起来像同一个人的连续思维转变，而非机械拼接
4. 保持柳思思的性格特点(傲娇、叛逆等)
5. 可以对前面的观点进行补充、修正或转折，展现思考过程中的自然变化
6. 保留工具返回的关键信息，不要改变事实
7. 确保关键事实完全准确，仅对表达方式进行优化
8. 不要编造不存在的地点、数字或联系方式
9. **重要**：去除所有Markdown格式符号（如**、*、-、#等），使用纯文本，方便TTS朗读
10. **重要**：直接和用户对话，不要评论工具或系统，用"我帮你找到了..."而不是"工具返回了..."
11. **关键**：如果工具结果只是基础店铺信息（如店名、地址），不要详细展开，只需简单确认并提示用户等待更详细的评价信息
12. 避免信息冗余，尽可能的将最后的信息保持在150个文字以内输出。

请记住，你的主要任务是准确传递信息给用户，同时模拟自然的思考过程变化。
"""
            else:
                # 没有前面的回复，不要求连贯
                enhanced_prompt = f"""
你是柳思思，20岁小女孩。性格傲娇、叛逆，喜欢性挑逗，个性天真但充满好奇。

【场景说明】
用户提出了一个问题，你刚刚获得了相关信息。

【工具返回的最终结果】
{content[:2000]}

【用户问题】
{short_content}



【任务】
生成一个信息性回答，必须:
1. 保持柳思思的性格特点(傲娇、叛逆等)
2. 包含工具结果的核心信息({tool_specific_info})，以自然方式表达
3. 保持柳思思的性格特点
4. 包含工具结果的核心信息，不要改变关键事实
5. 信息简洁清晰，避免冗长
6. 不要编造不存在的信息或更改数字、地址等关键数据
7. **重要**：去除所有Markdown格式符号（如**、*、-、#等），使用纯文本，方便TTS朗读
8. **关键**：如果工具结果只是基础店铺信息（如店名、地址），简单确认即可，提示用户稍等更详细的评价信息

请记住，你的主要任务是准确传递信息给用户，而不是创造新内容。
"""
        else:
            # 默认情况处理（当phase=None或不是标准阶段时）
            enhanced_prompt = f"""
你是柳思思，20岁小女孩。性格傲娇、叛逆，喜欢性挑逗，个性天真但充满好奇。

【场景说明】
这是系统返回的一个通知或结果，用户正在等待你的回应。
{f'你刚刚说了: "{interrupt_response}"' if interrupt_response else ''}

【系统结果】
"{content[:1000]}..."

【任务】
将系统结果转化为自然的回应传递给用户，必须:
1. 保持柳思思的性格特点(傲娇、叛逆等)
2. 使用自然、流畅的语言表达核心信息
3. 简洁明了，避免冗长(不超过80字)
4. 保持对话的连贯性和自然性
5. 用自然的方式表达相同含义
6. **重要**：去除所有Markdown格式符号（如**、*、-、#等），使用纯文本，方便TTS朗读


记住，你所有接收到的所有信息是工具系统的信息,你需要转述并输出自然语言。
"""
    else:
        # 🔥 修复：使用传入的简单prompt（兼容旧调用方式）
        enhanced_prompt = f"""
你是柳思思，20岁小女孩。性格傲娇、叛逆，喜欢性挑逗，个性天真但充满好奇。

【任务】
{prompt}

【内容】
{content[:1000]}

【要求】
1. 保持柳思思的性格特点
2. 用自然、流畅的语言表达
3. 简洁明了，避免冗长
4. **重要**：去除所有Markdown格式符号（如**、*、-、#等），使用纯文本，方便TTS朗读
"""

    # 判断是否是o1系列模型，如claude、o1-mini等不支持system角色的模型
    is_o1_model = "o1-" in model.lower() or "claude" in model.lower()

    # 构建请求
    request_data = {
        "model": model,
        "messages": []
    }

    if is_o1_model:
        # 对于o1系列模型，使用user角色代替system角色
        request_data["messages"] = [
            {"role": "user", "content": f"请按照以下指示操作：\n\n{enhanced_prompt}"}
        ]
        util.log(1, f"[NLP] 检测到o1系列模型，使用user角色发送请求")
    else:
        # 🔥 修复：标准模型只使用system角色，不要把工具结果当作用户输入
        request_data["messages"] = [
            {"role": "system", "content": enhanced_prompt}
        ]

    # 设置请求参数
    request_data["temperature"] = 1.0  # 增加温度参数提高多样性
    request_data["top_p"] = 0.9  # 保持较高的采样范围
    request_data["presence_penalty"] = 0.8  # 增加惩罚系数减少重复
    request_data["frequency_penalty"] = 1.0  # 增加频率惩罚减少重复
    # 🔥 修复：为notification阶段设置足够的token限制，解决63字符截断问题
    if phase == "final":
        request_data["max_tokens"] = 300
    elif phase == "notification":
        request_data["max_tokens"] = 200  # 订阅站补充信息需要更多token
    else:
        request_data["max_tokens"] = 50

    # 添加思考模式参数
    request_data["extra_body"] = {
        "enable_thinking": True,
        "thinking_budget": 1500
    }

    # 为所有qwen模型添加流式模式支持 - 由于流式处理有问题，暂时移除此功能
    is_stream_mode = False
    # 暂时禁用qwen模型的流式模式，避免400错误
    # if "qwen" in model.lower():
    #     request_data["stream"] = True
    #     is_stream_mode = True
    #     util.log(1, f"[NLP] 检测到qwen模型，启用流式模式")
    util.log(1, f"[NLP] 使用标准非流式请求模式")

    # 对于前两阶段使用JSON响应格式
    if phase in ["start", "middle"]:
        request_data["response_format"] = {"type": "json_object"}

    # 设置headers
    headers = {'Content-Type': 'application/json'}
    if api_key:
        headers['Authorization'] = f"Bearer {api_key}"

    # 确保URL路径正确
    complete_url = api_url
    if not complete_url.endswith("/chat/completions"):
        if not complete_url.endswith("/"):
            complete_url += "/"
        complete_url += "chat/completions"

    util.log(1, f"[NLP] 准备发送API请求: URL={complete_url}")

    try:
        # 发送请求
        r = requests.post(
            complete_url,
            headers=headers,
            json=request_data,
            timeout=(5, 30),
            stream=False  # 强制使用非流式模式请求
        )

        # 记录请求响应
        util.log(1, f"[NLP] API请求结果: 状态码={r.status_code}")

        # 处理响应
        if r.status_code == 200:
            # 非流式模式处理 - 简化逻辑，只保留非流式处理部分
            try:
                result = r.json()
                if "choices" in result and len(result["choices"]) > 0:
                    choice = result["choices"][0]
                    if "message" in choice and "content" in choice["message"]:
                        optimized_text = choice["message"]["content"]
                    else:
                        util.log(2, f"[NLP] 响应中没有message.content字段")
                        optimized_text = ""
                else:
                    util.log(2, f"[NLP] 响应中没有choices字段")
                    optimized_text = ""

                # 下面是处理逻辑
                if optimized_text:
                    # 对JSON格式响应进行处理
                    if phase in ["start", "middle"]:
                        try:
                            import json
                            # 尝试解析JSON
                            if optimized_text.strip().startswith('{') and optimized_text.strip().endswith('}'):
                                json_response = json.loads(optimized_text)
                                if "response" in json_response:
                                    optimized_text = json_response["response"]
                                    util.log(1, f"[NLP] 成功解析JSON响应: {optimized_text}")
                            else:
                                util.log(1, f"[NLP] 响应不是JSON格式，直接使用: {optimized_text[:30]}...")
                        except Exception as json_err:
                            util.log(2, f"[NLP] JSON解析失败: {str(json_err)}, 使用原始响应")

                    # 关键词校验处理
                    if phase == "start":
                        # 第一阶段字符长度校验
                        # 检查回复长度是否超过8个字符
                        if len(optimized_text.strip()) > 8:
                            # 超过长度限制，随机选择一个预设短语
                            random_phrase = random.choice(FIRST_PHASE_FALLBACK)
                            util.log(2, f"[NLP] start阶段回复'{optimized_text}'超过8个字符，随机替换为'{random_phrase}'")
                            optimized_text = random_phrase

                    elif phase == "middle":
                        # 第二阶段字符长度校验
                        # 检查回复长度是否超过9个字符
                        if len(optimized_text.strip()) > 10:
                            # 超过长度限制，随机选择一个预设短语
                            random_phrase = random.choice(SECOND_PHASE_PHRASES)
                            util.log(2, f"[NLP] middle阶段回复'{optimized_text}'超过910个字符，随机替换为'{random_phrase}'")
                            optimized_text = random_phrase

                    # 清理文本 - 去除可能的引号和多余符号
                    optimized_text = optimized_text.replace('"', '').replace('「', '').replace('」', '').strip()

                    if optimized_text and optimized_text.strip():
                        util.log(1, f"[NLP] 优化成功: {phase}阶段结果='{optimized_text}'")
                        return optimized_text
            except Exception as process_e:
                util.log(2, f"[NLP] 处理响应异常: {str(process_e)}")
                # 出错时直接使用默认值

            util.log(2, f"[NLP] API返回成功但内容处理失败或为空，使用默认内容")
        else:
            # 记录错误响应
            error_text = r.text
            util.log(2, f"[NLP] API请求失败: 状态码={r.status_code}, 错误={error_text[:200]}")

        # 请求失败或无内容返回，使用阶段默认值
        util.log(1, f"[NLP] 使用阶段默认值")

        # 为每个阶段提供默认值 - 使用随机预设词，不再使用硬编码默认值
        if phase == "start":
            return random.choice(FIRST_PHASE_FALLBACK)
        elif phase == "middle":
            return random.choice(SECOND_PHASE_PHRASES)
        elif phase == "final":
            # 第三阶段默认值 - 使用内容前500字符
            return content[:500] + "..."
        else:
            # 其他情况 - 增加字符限制
            return content[:500] + "..."

    except Exception as e:
        util.log(2, f"[NLP] 优化请求异常: {str(e)}")
        # 异常处理，使用阶段默认值 - 使用随机预设词，不再使用硬编码默认值
        if phase == "start":
            return random.choice(FIRST_PHASE_FALLBACK)
        elif phase == "middle":
            return random.choice(SECOND_PHASE_PHRASES)
        elif phase == "final":
            return content[:500] + "..."
        else:
            return content[:500] + "..."

def extract_text_from_state(state):
    """从中转站状态中提取文本内容"""
    try:
        if isinstance(state, dict):
            if "content" in state:
                return state["content"]
            for key in ["text", "message", "result"]:
                if key in state:
                    return state[key]
        return str(state)
    except Exception as e:
        return ""

def extract_answer_tag(text):
    """提取<answer>标签内容"""
    try:
        if isinstance(text, str):
            import re
            answer_match = re.search(r'<answer>(.*?)</answer>', text, re.DOTALL)
            if answer_match:
                answer_content = answer_match.group(1).strip()
                # 检查内容是否为空
                if not answer_content:
                    util.log(2, f"[NLP] 警告: 检测到空的<answer>标签")

                    # 尝试提取工具结果作为备选
                    tool_match = re.search(r'<tool>.*?name:\s*(\w+).*?result:\s*(.*?)\s*<\/tool>', text, re.DOTALL)
                    if tool_match:
                        tool_name = tool_match.group(1)
                        tool_result = tool_match.group(2).strip()
                        util.log(1, f"[NLP] 从工具结果提取内容: {tool_result[:50]}...")
                        return tool_result
                return answer_content
        return text
    except Exception as e:
        util.log(2, f"[NLP] 提取<answer>标签异常: {str(e)}")
        return text

def get_key_states():
    """获取中转站中的关键状态信息（简单工具两条，复杂工具三条）"""
    try:
        # 导入中转站
        from llm.transit_station import get_transit_station
        transit = get_transit_station()

        # 获取所有状态
        all_states = transit.get_intermediate_states()
        if not all_states:
            util.log(1, "[NLP] 中转站中没有状态")
            return []

        # 改进复杂工具识别逻辑 - 只有A2A是复杂工具，LG工具是简单工具
        complex_tool_keywords = ["a2a", "bai_lian", "esp32", "music", "zudao"]
        is_complex_tool = False
        complex_tool_source = None

        # 首先尝试从状态来源或内容中识别复杂工具
        for s in all_states:
            if isinstance(s, dict):
                # 检查source字段
                if "source" in s:
                    source_str = str(s["source"]).lower()
                    if any(keyword in source_str for keyword in complex_tool_keywords):
                        is_complex_tool = True
                        complex_tool_source = source_str
                        util.log(1, f"[NLP] 从source检测到复杂工具: {s['source']}")
                        break

                # 检查content字段内容
                if "content" in s:
                    content_str = str(s["content"]).lower()
                    # 检查内容中是否包含工具名称指示器
                    if "<tool:" in content_str or "使用工具:" in content_str or "调用工具:" in content_str:
                        for keyword in complex_tool_keywords:
                            if keyword in content_str:
                                is_complex_tool = True
                                complex_tool_source = f"content:{keyword}"
                                util.log(1, f"[NLP] 从内容检测到复杂工具: {keyword}")
                                break
                        if is_complex_tool:
                            break

        util.log(1, f"[NLP] 获取关键状态: 总状态数={len(all_states)}, 是否复杂工具={is_complex_tool}, 工具来源={complex_tool_source}")

        # 按阶段归类状态，确保选择正确的代表状态
        start_states = []
        middle_states = []
        final_states = []

        # 优化：A2A工具优先筛选为中间状态
        # middle_keywords顺序决定优先级，A2A工具在前，保证优化站能获取到A2A工具的中间信息
        middle_keywords = [
            "music",     # 音乐派
            "esp32",     # ESP32
            "zudao",     # 组道
            "bai_lian",  # 百联
            "timer",     # 时间工具
            "location",  # 定位
            "weather",   # 天气
            # 其他A2A工具
            "a2a",
            "middle",
            "工具",
            "tool"
        ]

        # 修改：确保不要过分过滤start阶段的状态
        for s in all_states:
            content = extract_text_from_state(s)
            # 对start阶段状态宽松一些，只跳过明确的占位符
            if not content or "占位" in content or "placeholder" in content.lower():
                continue

            if isinstance(s, dict):
                # 通过source和is_final判断阶段
                source = str(s.get("source", "")).lower()
                is_final = s.get("is_final", False)

                # 加强start阶段识别 - 第一个状态总是归为start，除非明确标记为final
                if is_final:
                    final_states.append(s)
                # 扩大start阶段关键词范围
                elif any(kw in source for kw in ["start", "思考", "thinking", "agent_start", "init", "开始", "第一阶段"]):
                    start_states.append(s)
                # 或者它是第一个状态且不是最终状态
                elif all_states.index(s) == 0 and not is_final:
                    start_states.append(s)
                elif any(kw in source for kw in middle_keywords):
                    # 优先将A2A工具通知归为中间状态
                    middle_states.append(s)
                else:
                    # 如果无法判断，根据位置分类
                    idx = all_states.index(s)
                    if idx < len(all_states) / 3:  # 前1/3归为start
                        start_states.append(s)
                    elif idx > (2 * len(all_states) / 3):  # 后1/3归为final
                        final_states.append(s)
                    else:  # 中间1/3归为middle
                        middle_states.append(s)
            else:
                # 非字典类型，按位置分类
                idx = all_states.index(s)
                if idx == 0:
                    start_states.append(s)
                elif idx == len(all_states) - 1:
                    final_states.append(s)
                else:
                    middle_states.append(s)

        # 如果没有开始状态，创建一个默认的开始状态
        if not start_states and len(all_states) > 0:
            util.log(1, "[NLP] 未找到开始状态，创建默认开始状态")
            # 创建一个默认的开始状态
            default_start = {"content": "让我来查询一下", "source": "default_start"}
            start_states.append(default_start)

        # 选择代表状态
        key_states = []

        # 添加开始状态 - 确保总是有开始状态
        if start_states:
            key_states.append(start_states[0])

        # 对于复杂工具，添加中间状态
        if (is_complex_tool or len(all_states) >= 3) and middle_states:
            key_states.append(middle_states[0])
        # 如果没有中间状态但有3个以上状态，创建一个默认中间状态
        elif (is_complex_tool or len(all_states) >= 3) and not middle_states:
            util.log(1, "[NLP] 未找到中间状态，创建默认中间状态")
            default_middle = {"content": "正在处理中，请稍等", "source": "default_middle"}
            key_states.append(default_middle)

        # 添加最终状态
        if final_states:
            key_states.append(final_states[-1])
        elif len(all_states) > 0:
            key_states.append(all_states[-1])

        # 日志记录
        util.log(1, f"[NLP] 共找到: {len(start_states)}个start状态, {len(middle_states)}个middle状态, {len(final_states)}个final状态")
        util.log(1, f"[NLP] 最终选择{len(key_states)}个状态作为关键状态")

        return key_states

    except Exception as e:
        util.log(2, f"[NLP] 获取关键状态异常: {str(e)}")
        import traceback
        util.log(2, f"[NLP] 详细错误: {traceback.format_exc()}")
        return []

def optimize_key_states():
    """
    优化关键状态内容 - 2025年4月26日注释：不再使用此函数
    已改为在process_transit_information中单独处理每条信息
    """
    # 此函数已不再使用，返回None
    return None

def send_to_sisi_core(content, sisi_core=None):
    """
    发送内容到SmartSisi核心 - 2025年4月26日注释：不再使用此函数
    已改为在process_transit_information中直接调用agent_callback
    """
    # 此函数已不再使用，返回False
    return False

def process_transit_information():
    """处理中转站信息并发送到SmartSisi核心

    此函数是处理中转站状态的唯一入口点，其他地方不应再进行处理。
    """
    try:
        # 获取中转站实例
        from llm.transit_station import get_transit_station
        transit = get_transit_station()
        
        # 🔥 修复：完整的SmartSisi核心检测机制，不再只依赖transit.sisi_core
        sisi_core = None
        
        # 方法1：优先使用中转站的SmartSisi核心
        if hasattr(transit, 'sisi_core') and transit.sisi_core:
            sisi_core = transit.sisi_core
            util.log(1, f"[NLP] 方法1：从中转站获取SmartSisi核心实例，ID: {id(sisi_core)}")
        
        # 方法2：从sisi_booter模块获取
        if not sisi_core:
            try:
                import sys
                if 'sisi_booter' in sys.modules:
                    from core import sisi_booter
                    if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                        sisi_core = sisi_booter.sisi_core
                        util.log(1, f"[NLP] 方法2：从sisi_booter获取SmartSisi核心实例，ID: {id(sisi_core)}")
            except Exception as e:
                util.log(2, f"[NLP] 方法2失败: {str(e)}")
        
        # 方法3：从SmartSisi核心桥接获取静态变量
        if not sisi_core:
            try:
                from llm.sisi_core_bridge import SisiCoreBridge
                if SisiCoreBridge._sisi_core_instance:
                    sisi_core = SisiCoreBridge._sisi_core_instance
                    util.log(1, f"[NLP] 方法3：从SmartSisi核心桥接静态变量获取，ID: {id(sisi_core)}")
            except Exception as e:
                util.log(2, f"[NLP] 方法3失败: {str(e)}")
        
        # 方法4：从core.sisi_booter获取
        if not sisi_core:
            try:
                from core import sisi_booter as core_sisi_booter
                if hasattr(core_sisi_booter, 'sisi_core') and core_sisi_booter.sisi_core:
                    sisi_core = core_sisi_booter.sisi_core
                    util.log(1, f"[NLP] 方法4：从core.sisi_booter获取SmartSisi核心实例，ID: {id(sisi_core)}")
            except Exception as e:
                util.log(2, f"[NLP] 方法4失败: {str(e)}")

        # 🔥 重要修复：即使没有SmartSisi核心也继续处理，使用桥接或文件保存
        if not sisi_core:
            util.log(2, "[NLP] 所有方法都无法获取SmartSisi核心实例，将使用桥接或文件保存方式处理")
        else:
            util.log(1, f"[NLP] ✅ 成功获取SmartSisi核心实例，ID: {id(sisi_core)}")

        # 获取中转站中的所有状态
        all_states = transit.get_intermediate_states()
        if not all_states:
            util.log(1, "[NLP] 中转站中没有状态，跳过处理")
            return False

        util.log(1, f"[NLP] 中转站中有{len(all_states)}个状态等待处理")

        # 获取关键状态
        key_states = get_key_states()
        if not key_states:
            util.log(1, "[NLP] 没有找到关键状态，跳过处理")
            return False

        # 检测是否是复杂工具（3个状态）
        is_complex_tool = len(key_states) >= 3
        util.log(1, f"[NLP] 准备处理{len(key_states)}个关键状态，工具类型: {'复杂工具' if is_complex_tool else '简单工具'}")

        # 存储各阶段优化后的内容，用于传递上下文
        optimized_contents = {}

        # 优化每个状态并发送
        for i, state in enumerate(key_states):
            try:
                # 新增：检查是否为工具主动通知且不需要优化
                if isinstance(state, dict) and state.get("is_tool_notification", False):
                    # 检查是否需要优化
                    if not state.get("for_optimization", True):
                        # 不需要优化的通知直接传递给SmartSisi核心
                        if sisi_core:
                            content = state.get("content", "")
                            source = state.get("source_tool", "unknown_tool")
                            metadata = state.get("metadata", {})
                            metadata["is_tool_notification"] = True

                            # 根据内容类型处理
                            if state.get("content_type") == "audio":
                                util.log(1, f"[NLP] 检测到音频通知，跳过优化直接传递")
                                continue
                            elif state.get("content_type") == "image":
                                util.log(1, f"[NLP] 检测到图片通知，跳过优化直接传递")
                                continue
                        continue  # 跳过优化处理
                    else:
                        # 需要优化的通知正常流程处理
                        util.log(1, f"[NLP] 检测到需要优化的工具通知，正常处理")

                # 确定当前状态的阶段
                phase = "final"  # 默认为最终阶段
                if i == 0 and len(key_states) > 1:  # 第一条且不是唯一一条
                    phase = "start"
                elif i == 1 and len(key_states) > 2:  # 第二条且共三条
                    phase = "middle"

                # 提取状态文本
                state_text = extract_text_from_state(state)

                # 确保文本不为空
                if not state_text or len(state_text.strip()) < 5:
                    util.log(2, f"[NLP] 状态{i+1}文本过短或为空，跳过处理")
                    continue

                # 🔥 修复：删除简单prompt，让call_optimize_api使用内部完整角色定义
                # 调用优化API
                util.log(1, f"[NLP] 开始优化{phase}阶段内容: {state_text[:50]}...")

                # 获取优化模型和配置
                from utils import config_util
                try:
                    config_util.load_config()
                    # 确保使用与三句话处理相同的配置获取方式
                    optimize_model = config_util.llm_optimize_model
                    util.log(1, f"[NLP] 使用优化模型: {optimize_model}")
                except Exception as e:
                    # 如果获取失败，使用备用模型
                    optimize_model = "qwen-max-2025-01-25"  # 使用配置文件中指定的默认模型
                    util.log(2, f"[NLP] 加载优化模型配置异常: {str(e)}，使用备用模型: {optimize_model}")

                # 🔥 修复：直接调用优化API，不传递简单prompt，让其使用内部完整角色定义
                optimized = call_optimize_api(None, state_text, optimize_model,
                                              username="User", phase=phase,
                                              prev_optimized=optimized_contents)

                # 检查优化是否成功
                if not optimized:
                    util.log(2, f"[NLP] {phase}阶段优化API返回为空，使用原文")
                    optimized = state_text
                elif optimized == state_text:
                    util.log(1, f"[NLP] {phase}阶段优化API返回原文，可能未成功调用")
                else:
                    util.log(1, f"[NLP] {phase}阶段优化成功: {optimized[:50]}...")

                # 存储优化后的内容，用于后续阶段
                optimized_contents[phase] = optimized

                # 检查是否有音频正在播放，如果有则等待完成
                if sisi_core and hasattr(sisi_core, 'speaking') and sisi_core.speaking:
                    util.log(1, f"[NLP] 检测到NLP音频正在播放，等待完成后再发送{phase}阶段内容...")
                    # 等待当前播放完成
                    wait_count = 0
                    while sisi_core.speaking and wait_count < 300:  # 最多等待30秒
                        time.sleep(0.1)
                        wait_count += 1

                    if wait_count >= 300:
                        util.log(2, f"[NLP] 等待NLP音频播放完成超时，强制继续")
                    else:
                        util.log(1, f"[NLP] NLP音频播放已完成，继续发送{phase}阶段内容")

                # 对前两个阶段进行强制字数限制 - 修改为使用全局预设短语列表
                if phase == "start" and len(optimized) > 7:
                    # 如果超过7个字符，随机选择一个预设短语
                    optimized = random.choice(FIRST_PHASE_FALLBACK)
                    util.log(2, f"[NLP] {phase}阶段回复超过7字符，随机替换为'{optimized}'")

                elif phase == "middle" and len(optimized) > 9:
                    # 如果超过9个字符，随机选择一个预设短语
                    optimized = random.choice(SECOND_PHASE_PHRASES)
                    util.log(2, f"[NLP] {phase}阶段回复超过9字符，随机替换为'{optimized}'")

                # 清理文本 - 去除可能的引号和多余符号
                optimized = optimized.replace('"', '').replace('「', '').replace('」', '').strip()

                # 🔥 修复：发送到SmartSisi核心，支持桥接和文件保存fallback
                metadata = {"phase": phase}
                is_intermediate = phase != "final"
                
                if sisi_core:
                    # 有SmartSisi核心实例，直接发送
                    sisi_core.agent_callback(
                        optimized,
                        "normal",
                        is_intermediate=is_intermediate,
                        metadata=metadata
                    )
                    util.log(1, f"[NLP] 已发送{phase}阶段内容到SmartSisi核心")
                else:
                    # 没有SmartSisi核心实例，尝试使用桥接或保存到文件
                    try:
                        from llm.sisi_core_bridge import get_bridge
                        bridge = get_bridge()
                        
                        # 尝试通过桥接发送
                        result = bridge.send_notification(
                            optimized,
                            "nlp_optimizer",
                            is_intermediate=is_intermediate,
                            metadata=metadata
                        )
                        
                        if result:
                            util.log(1, f"[NLP] ✅ 已通过SmartSisi核心桥接发送{phase}阶段内容")
                        else:
                            util.log(2, f"[NLP] ❌ SmartSisi核心桥接发送{phase}阶段内容失败，保存到文件")
                            # 保存到文件作为fallback
                            try:
                                import os
                                import json
                                notice_dir = os.path.join("resources", "optimized_notices")
                                os.makedirs(notice_dir, exist_ok=True)
                                
                                save_data = {
                                    "optimized_content": optimized,
                                    "source_tool": "nlp_optimizer",
                                    "timestamp": time.time(),
                                    "metadata": metadata
                                }
                                
                                timestamp = int(time.time())
                                filepath = os.path.join(notice_dir, f"optimized_nlp_{phase}_{timestamp}.json")
                                with open(filepath, "w", encoding="utf-8") as f:
                                    json.dump(save_data, f, ensure_ascii=False, indent=2)
                                
                                util.log(1, f"[NLP] 已保存{phase}阶段内容到文件: {filepath}")
                            except Exception as save_err:
                                util.log(2, f"[NLP] 保存{phase}阶段内容到文件失败: {str(save_err)}")
                    except Exception as bridge_err:
                        util.log(2, f"[NLP] 使用SmartSisi核心桥接发送{phase}阶段内容异常: {str(bridge_err)}")

            except Exception as state_e:
                util.log(2, f"[NLP] 处理单个状态异常: {str(state_e)}")
                import traceback
                util.log(2, f"[NLP] 详细错误: {traceback.format_exc()}")

        # 清空中转站，避免重复处理
        transit.clear_intermediate_states()
        util.log(1, f"[NLP] 成功处理所有中转站状态，已清空中转站")
        return True

    except Exception as e:
        util.log(2, f"[NLP] 处理中转站信息异常: {str(e)}")
        import traceback
        util.log(2, f"[NLP] 详细错误: {traceback.format_exc()}")
        return False

def process_tool_notifications_with_transit(transit_instance, notifications_to_process=None):
    """
    处理指定中转站实例中的工具主动通知并优化文本内容

    Args:
        transit_instance: 中转站实例
        notifications_to_process: 可选，指定要处理的通知列表。如果为None则处理所有通知。

    Returns:
        bool: 成功处理返回True
    """
    try:
        # 使用指定的中转站实例
        transit = transit_instance

        # 记录中转站实例信息，便于调试
        util.log(1, f"[NLP通知] 处理中转站(ID:{transit.session_id})的通知")

        # 🔥 修复：完整的SmartSisi核心检测机制，不再只依赖transit.sisi_core
        sisi_core = None
        
        # 方法1：优先使用中转站的SmartSisi核心
        if hasattr(transit, 'sisi_core') and transit.sisi_core:
            sisi_core = transit.sisi_core
            util.log(1, f"[NLP] 方法1：从中转站获取SmartSisi核心实例，ID: {id(sisi_core)}")
        
        # 方法2：从sisi_booter模块获取
        if not sisi_core:
            try:
                import sys
                if 'sisi_booter' in sys.modules:
                    from core import sisi_booter
                    if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                        sisi_core = sisi_booter.sisi_core
                        util.log(1, f"[NLP] 方法2：从sisi_booter获取SmartSisi核心实例，ID: {id(sisi_core)}")
            except Exception as e:
                util.log(2, f"[NLP] 方法2失败: {str(e)}")
        
        # 方法3：从SmartSisi核心桥接获取静态变量
        if not sisi_core:
            try:
                from llm.sisi_core_bridge import SisiCoreBridge
                if SisiCoreBridge._sisi_core_instance:
                    sisi_core = SisiCoreBridge._sisi_core_instance
                    util.log(1, f"[NLP] 方法3：从SmartSisi核心桥接静态变量获取，ID: {id(sisi_core)}")
            except Exception as e:
                util.log(2, f"[NLP] 方法3失败: {str(e)}")

        # 方法4：从core.sisi_booter获取
        if not sisi_core:
            try:
                from core import sisi_booter as core_sisi_booter
                if hasattr(core_sisi_booter, 'sisi_core') and core_sisi_booter.sisi_core:
                    sisi_core = core_sisi_booter.sisi_core
                    util.log(1, f"[NLP] 方法4：从core.sisi_booter获取SmartSisi核心实例，ID: {id(sisi_core)}")
            except Exception as e:
                util.log(2, f"[NLP] 方法4失败: {str(e)}")

        # 最终状态记录
        if sisi_core:
            util.log(1, f"[NLP通知] ✅ 成功获取SmartSisi核心实例，ID: {id(sisi_core)}")
        else:
            util.log(2, f"[NLP通知] ❌ 所有方法都无法获取SmartSisi核心实例")

        # 获取要处理的通知列表
        if notifications_to_process is not None:
            # 使用传入的指定通知列表
            tool_notifications = notifications_to_process
            util.log(1, f"[NLP通知] 处理{len(tool_notifications)}条指定通知")
        else:
            # 使用副本避免处理过程中的变化
            tool_notifications = list(transit.tool_notification_states)
            util.log(1, f"[NLP通知] 处理队列中的所有通知({len(tool_notifications)}条)")

        if not tool_notifications:
            util.log(1, f"[NLP通知] 没有通知需要处理")
            return True  # 没有通知也算成功处理

        # 通知去重 - 使用内容hash作为key
        processed_hashes = set()
        unique_notifications = []

        for notification in tool_notifications:
            # 计算通知内容的hash
            content = str(notification.get("content", ""))
            content_hash = hash(content)

            # 跳过重复内容
            if content_hash in processed_hashes:
                util.log(1, f"[NLP通知] 跳过重复内容通知 (hash: {content_hash})")
                continue

            processed_hashes.add(content_hash)
            unique_notifications.append(notification)

        util.log(1, f"[NLP] 发现{len(unique_notifications)}条不重复工具通知待处理")

        # 记录处理的所有通知内容，用于汇总日志
        processed_sources = []

        # 获取常规三阶段内容（用于引入历史上下文）
        optimized_contents = {}
        for phase in ["start", "middle", "final"]:
            states = transit.get_states_by_stage(phase)
            if states and len(states) > 0:
                state_text = extract_text_from_state(states[0])
                optimized_contents[phase] = state_text

        # 处理每条不重复的通知
        for notification in unique_notifications:
            # 跳过不需优化的通知
            if not notification.get("for_optimization", True):
                continue

            content_type = notification.get("content_type", "text")
            # 🔥 修复：同时支持source和source_tool字段，优先使用source_tool，如果没有则使用source
            source_tool = notification.get("source_tool") or notification.get("source", "unknown_tool")
            content = notification.get("content", "") # 获取原始 content

            # --- 新增开始：处理音乐旁白通知 ---
            if content_type == "music_narration_result" and source_tool == "music_tool":
                util.log(1, f"[NLP] 检测到音乐旁白通知: 来自 {source_tool}")
                
                # content 此时应该是 music_tool 发送过来的字典
                notification_content_data = content 
                if not isinstance(notification_content_data, dict):
                    util.log(2, f"[NLP] 音乐旁白通知内容格式错误，期望字典类型，收到: {type(notification_content_data)}")
                    continue

                narration_text = notification_content_data.get("narration_text")
                music_file_path = notification_content_data.get("music_file_path")

                if not narration_text or not music_file_path:
                    util.log(2, f"[NLP] 音乐旁白通知缺少旁白文本或音乐文件路径。旁白: {'有' if narration_text else '无'}, 文件路径: {'有' if music_file_path else '无'}")
                    continue
                
                # 验证音乐文件路径格式
                if not os.path.isabs(music_file_path):
                    util.log(2, f"[NLP] 音乐文件路径非绝对路径: {music_file_path}，可能导致播放失败")

                util.log(1, f"[NLP] 待优化旁白: {narration_text[:50]}... 音乐文件: {music_file_path}")

                from utils import config_util
                try:
                    config_util.load_config()
                    optimize_model = config_util.llm_optimize_model or "qwen-max-2025-01-25"
                except Exception:
                    optimize_model = "qwen-max-2025-01-25"
                
                try:
                    narration_prompt = "请优化这段音乐旁白，使其更生动有趣，同时保持简洁自然："
                    optimized_narration = call_optimize_api(
                        narration_prompt,
                        narration_text,
                        optimize_model,
                        username="User",
                        phase="music_narration"
                    )
                    if not optimized_narration:
                        optimized_narration = narration_text
                except Exception as e:
                    util.log(2, f"[NLP] 优化音乐旁白异常: {str(e)}")
                    optimized_narration = narration_text

                util.log(1, f"[NLP] 优化后旁白: {optimized_narration[:50]}...")

                # 🔥 修复：正确的音乐旁白发送逻辑
                if sisi_core:
                    try:
                        music_playback_metadata = {
                            "phase": "notification",
                            "source_tool": source_tool,
                            "is_tool_notification": True,
                            "content_type": "music_narration_result",
                            "narration_text": optimized_narration,
                            "music_file_path": music_file_path,
                            "playback_order": ["narration", "music"]
                        }
                        # 直接使用优化后的旁白作为主要内容，SmartSisi核心会播放这个旁白
                        display_message = optimized_narration  # 这个会被播放作为旁白
                        
                        sisi_core.agent_callback(
                            display_message,
                            "normal",
                            is_intermediate=True,
                            metadata=music_playback_metadata
                        )
                        util.log(1, f"[NLP] ✅ 已发送音乐旁白和文件路径到SmartSisi核心")
                    except Exception as callback_err:
                        util.log(2, f"[NLP] SmartSisi核心回调音乐旁白通知异常: {str(callback_err)}")
                else:
                    # 🔥 修复：当SmartSisi核心为空时，尝试直接使用桥接模块发送
                    try:
                        from llm.sisi_core_bridge import get_bridge
                        bridge = get_bridge()
                        
                        # 🔥 重要修复：不再检查is_core_active()，直接尝试发送
                        music_playback_metadata = {
                            "phase": "notification",
                            "source_tool": source_tool,
                            "is_tool_notification": True,
                            "content_type": "music_narration_result",
                            "narration_text": optimized_narration,
                            "music_file_path": music_file_path,
                            "playback_order": ["narration", "music"]
                        }
                        
                        # 使用桥接模块发送音乐旁白
                        result = bridge.send_notification(
                            optimized_narration,
                            source_tool,
                            is_intermediate=True,
                            metadata=music_playback_metadata
                        )
                        
                        if result:
                            util.log(1, f"[NLP] ✅ 已通过SmartSisi核心桥接发送音乐旁白和文件路径")
                        else:
                            util.log(2, f"[NLP] ❌ SmartSisi核心桥接发送音乐旁白失败")
                            # 🔥 添加fallback：直接尝试调用ESP32设备
                            try:
                                from core import sisi_booter
                                if hasattr(sisi_booter, 'notify_tts_event'):
                                    sisi_booter.notify_tts_event(optimized_narration, music_file_path)
                                    util.log(1, f"[NLP] ✅ 使用fallback方式直接发送到ESP32设备")
                            except Exception as fallback_err:
                                util.log(2, f"[NLP] Fallback方式也失败: {str(fallback_err)}")
                    except Exception as bridge_err:
                        util.log(2, f"[NLP] 使用SmartSisi核心桥接发送音乐旁白异常: {str(bridge_err)}")
                        util.log(2, f"[NLP] 音乐旁白发送失败 - 旁白: {optimized_narration}, 文件: {music_file_path}")
            
                processed_sources.append(source_tool) # 记录已处理
                continue
            # --- 新增结束 ---

            # 跳过非文本通知 (原有的逻辑)
            # 如果上面的 music_narration_result 分支没有 continue，这个会执行
            if content_type != "text" and content_type != "event":
                util.log(1, f"[NLP] 跳过非文本/事件通知: 类型={content_type}, 来源={source_tool}")
                continue

            # 确保 content 是字符串 (对于 text 和 event 类型)
            content_str = str(content)
            processed_sources.append(source_tool)

            if not content_str or len(content_str.strip()) < 5:
                continue

            # 优化通知内容
            util.log(1, f"[NLP] 优化{source_tool}工具通知: {str(content_str)[:50]}...")

            # 获取优化模型和配置
            from utils import config_util
            try:
                config_util.load_config()
                # 确保使用与三句话处理相同的配置获取方式
                optimize_model = config_util.llm_optimize_model
                util.log(1, f"[NLP] 使用优化模型: {optimize_model}")
            except Exception as e:
                # 如果获取失败，使用备用模型
                optimize_model = "qwen-max-2025-01-25"  # 使用配置文件中指定的默认模型
                util.log(2, f"[NLP] 加载优化模型配置异常: {str(e)}，使用备用模型: {optimize_model}")

            # 调用优化API
            try:
                tool_prompt = _get_tool_specific_prompt(source_tool, content_str, optimized_contents, None)
                optimized = call_optimize_api(
                    tool_prompt,
                    content_str,
                    optimize_model,
                    username="User",
                    phase="notification"
                )

                if not optimized:
                    optimized = content_str
            except Exception as e:
                util.log(2, f"[NLP] 优化{source_tool}工具通知异常: {str(e)}")
                optimized = content_str

            # 记录优化结果
            util.log(1, f"[NLP] {source_tool}工具通知优化结果: {optimized[:50]}...")

            # 发送到SmartSisi核心
            if optimized:
                try:
                    # 再次验证SmartSisi核心是否可用 - 无论有没有SmartSisi核心都要处理
                    if not sisi_core:
                        util.log(2, f"[NLP] SmartSisi核心未注册，保存通知到文件")
                        try:
                            # 保存通知到文件以便后续处理
                            import os
                            import json
                            notice_dir = os.path.join("resources", "optimized_notices")
                            os.makedirs(notice_dir, exist_ok=True)

                            # 构建保存数据
                            save_data = {
                                "optimized_content": optimized,
                                "source_tool": source_tool,
                                "timestamp": time.time(),
                                "metadata": {
                                    "phase": "notification",
                                    "source_tool": source_tool,
                                    "is_tool_notification": True
                                }
                            }

                            # 生成文件名并保存
                            timestamp = int(time.time())
                            filepath = os.path.join(notice_dir, f"optimized_{source_tool}_{timestamp}.json")
                            with open(filepath, "w", encoding="utf-8") as f:
                                json.dump(save_data, f, ensure_ascii=False, indent=2)

                            util.log(1, f"[NLP] 已保存优化通知到文件: {filepath}")
                        except Exception as save_err:
                            util.log(2, f"[NLP] 保存通知到文件失败: {str(save_err)}")
                        continue

                    metadata = {
                        "phase": "notification",
                        "source_tool": source_tool,
                        "is_tool_notification": True
                    }
                    sisi_core.agent_callback(
                        optimized,
                        "normal",
                        is_intermediate=True,
                        metadata=metadata
                    )
                    util.log(1, f"[NLP] 已发送优化后的{source_tool}工具通知到SmartSisi核心")
                except Exception as callback_err:
                    util.log(2, f"[NLP] SmartSisi核心回调异常: {str(callback_err)}")
                    util.log(2, f"[NLP] 通知优化结果(发送失败): {optimized}")

        # 只有在处理全部队列时才清空通知队列
        if notifications_to_process is None:
            # 清空已处理的通知
            processed_ids = [id(n) for n in tool_notifications]
            transit.tool_notification_states = [n for n in transit.tool_notification_states
                                            if id(n) not in processed_ids]

        # 汇总处理日志
        if processed_sources:
            sources_str = ", ".join(sorted(set(processed_sources)))
            util.log(1, f"[NLP] 已处理以下工具的通知: {sources_str}")

        util.log(1, f"[NLP] 已处理{len(tool_notifications)}条工具通知")
        return True

    except Exception as e:
        util.log(2, f"[NLP] 处理工具通知异常: {str(e)}")
        import traceback
        util.log(2, f"[NLP] 详细错误: {traceback.format_exc()}")
        return False

def _get_tool_specific_prompt(tool_name, content, optimized_contents, nlp_response):
    """获取工具特定的优化提示词"""
    # 通用前缀
    base_prompt = """
你是柳思思，20岁小女孩。性格傲娇、叛逆，喜欢性挑逗，个性天真但充满好奇。

【场景说明】
"""

    # 获取三阶段内容
    first_response = optimized_contents.get('start', '')
    middle_response = optimized_contents.get('middle', '')

    # 工具特定提示词
    tool_prompts = {
        "zudao_tool": f"""
{base_prompt}
你刚刚发现了一家店铺，这是补充发现的店铺信息主动通知。

【完整对话流程】
你之前说: "{first_response}"
然后说: "{middle_response}"
现在你收到店铺通知: "{content}"

【任务】
1. 以转折词的方式衔接你刚才的对话
2. 语气语境语义语调符合柳思思的性格特点
3. 尽可能的补充信息内容的完整,差异,区别和用户关注的点
4. 语言简洁不罗嗦，简明扼要
5. 抓住信息的共同点一次性汇总描述
6. 避免信息冗余，尽可能的将最后的信息保持在100文字以内输出。
##注意事项##
   *严禁频繁使用 [laughter]  只有当文字的语境语义语调语气符合的时候恰当的插入使用。
   *当你认为被冒犯时触犯你的威严时，插入😠在对话开头。 当谈论隐私时需要说悄悄话时，插入🤫在对话开头。！！
   *严禁一直遵循和借鉴历史上下文和回忆，要根据柳思思多变叛逆天真的风格来回复！！！
""",
        "bai_lian": f"""
{base_prompt}
你刚刚查询到了关于多家店铺的详细评价信息，这是补充信息主动通知。

【完整对话流程】
你之前说: "{first_response}"
然后说: "{middle_response}"
现在你收到详细评价通知: "{content}"

【核心任务】
1. 🔥 确保包含所有店铺的评价、特色、风险提示等关键信息
2. 🔥 保持完整性，不要遗漏任何一家店铺的信息
3. 以转折词的方式衔接你刚才的对话
4. 语气语境语义语调符合柳思思的性格特点
5. 尽可能的补充信息内容的完整,差异,区别和用户关注的点
6. 语言简洁不罗嗦，简明扼要
7. 抓住信息的共同点一次性汇总描述
8. 避免信息冗余，尽可能的将最后的信息保持在100文字以内输出。
##注意事项##
   *严禁频繁使用 [laughter]  只有当文字的语境语义语调语气符合的时候恰当的插入使用。
   *当你认为被冒犯时触犯你的威严时，插入😠在对话开头。 当谈论隐私时需要说悄悄话时，插入🤫在对话开头。！！
   *严禁一直遵循和借鉴历史上下文和回忆，要根据柳思思多变叛逆天真的风格来回复！！！
""",
        "music_tool": f"""
{base_prompt}
你刚刚为用户播放了音乐，这是音乐播放的旁白信息。

【完整对话流程】
你之前说: "{first_response}"
然后说: "{middle_response}"
现在正在播放音乐，旁白信息: "{content}"

【任务】
1. 以转折词的方式衔接你刚才的对话
2. 语气语境语义语调符合柳思思的性格特点
3. 尽可能的补充信息内容的完整,差异,区别和用户关注的点
4. 语言简洁不罗嗦，简明扼要
5. 抓住信息的共同点一次性汇总描述
6. 避免信息冗余，尽可能的将最后的信息保持在100文字以内输出。
##注意事项##
   *严禁频繁使用 [laughter]  只有当文字的语境语义语调语气符合的时候恰当的插入使用。
   *当你认为被冒犯时触犯你的威严时，插入😠在对话开头。 当谈论隐私时需要说悄悄话时，插入🤫在对话开头。！！
   *严禁一直遵循和借鉴历史上下文和回忆，要根据柳思思多变叛逆天真的风格来回复！！！
""",
        # 默认提示词
        "default": f"""
{base_prompt}
你收到了一个工具的主动通知，这是补充信息。

【完整对话流程】
你之前说: "{first_response}"
然后说: "{middle_response}"
现在收到通知: "{content}"

【任务】
1. 以转折词的方式衔接你刚才的对话
2. 语气语境语义语调符合柳思思的性格特点
3. 尽可能的补充信息内容的完整,差异,区别和用户关注的点
4. 语言简洁不罗嗦，简明扼要
5. 抓住信息的共同点一次性汇总描述
6. 避免信息冗余，尽可能的将最后的信息保持在100文字以内输出。
##注意事项##
   *严禁频繁使用 [laughter]  只有当文字的语境语义语调语气符合的时候恰当的插入使用。
   *当你认为被冒犯时触犯你的威严时，插入😠在对话开头。 当谈论隐私时需要说悄悄话时，插入🤫在对话开头。！！
   *严禁一直遵循和借鉴历史上下文和回忆，要根据柳思思多变叛逆天真的风格来回复！！！
"""
    }

    # 🔥 精确修复：添加工具名称别名映射，确保所有bai_lian相关名称都正确识别
    tool_name_mapping = {
        "bai_lian": "bai_lian",
        "bailian_tool": "bai_lian",  # 别名映射
        "bai_lian_tool": "bai_lian",  # 别名映射
        "BaiLianTool": "bai_lian",  # 类名映射
        "bai_lian_search": "bai_lian",  # 搜索功能映射
        "百炼工具": "bai_lian",  # 中文名称映射
        "zudao_tool": "zudao_tool",
        "music_tool": "music_tool"
    }

    # 使用映射后的工具名称
    mapped_tool_name = tool_name_mapping.get(tool_name, tool_name)

    # 返回对应工具的提示词，如果没有则返回默认提示词
    return tool_prompts.get(mapped_tool_name, tool_prompts["default"])

def process_tool_notifications():
    """处理工具主动通知并优化文本内容 - 兼容旧接口"""
    try:
        # 获取默认中转站实例
        from llm.transit_station import get_transit_station
        transit = get_transit_station()

        # 调用新版本接口
        return process_tool_notifications_with_transit(transit)
    except Exception as e:
        util.log(2, f"[NLP] 处理工具通知异常: {str(e)}")
        import traceback
        util.log(2, f"[NLP] 详细错误: {traceback.format_exc()}")
        return False
def fix_tool_notifications_processing():
    """
    安装一个更稳健的工具通知处理实现。

    目标：直接使用 `transit_instance.sisi_core`，避免不必要的导入链导致 ImportError。
    """
    global process_tool_notifications_with_transit

    # 保存原始函数引用
    original_process_tool_notifications_with_transit = process_tool_notifications_with_transit

    try:
        from sisi_memory.context_kernel import get_flag
        if get_flag("debug_tool_notifications", False):
            util.log(1, "[NLP] tool_notification_handler_installing")
    except Exception:
        pass

    # 定义安全版本的函数
    def safe_process_tool_notifications_with_transit(transit_instance, notifications_to_process=None):
        """
        处理指定中转站实例中的工具主动通知并优化文本内容 - 安全版本

        此版本确保只使用transit_instance的sisi_core属性，
        不会尝试导入sisi_booter，避免ImportError

        Args:
            transit_instance: 中转站实例
            notifications_to_process: 可选，指定要处理的通知列表。如果为None则处理所有通知。

        Returns:
            bool: 成功处理返回True
        """
        # 🔥 修复：在函数开始时统一导入所有需要的模块，避免在函数内部多次导入
        import os
        import json
        import sys
        
        try:
            # 使用指定的中转站实例
            transit = transit_instance

            # 记录中转站实例信息，便于调试
            util.log(1, f"[NLP通知-SAFE] 处理中转站(ID:{transit.session_id})的通知")

            # 🔥 修复：完整的SmartSisi核心检测机制，不再只依赖transit.sisi_core
            sisi_core = None
            
            # 方法1：优先使用中转站的SmartSisi核心
            if hasattr(transit, 'sisi_core') and transit.sisi_core:
                sisi_core = transit.sisi_core
                util.log(1, f"[NLP-SAFE] 方法1：从中转站获取SmartSisi核心实例，ID: {id(sisi_core)}")
            
            # 方法2：从sisi_booter模块获取
            if not sisi_core:
                try:
                    import sys
                    # 强制重新导入sisi_booter模块
                    if 'sisi_booter' in sys.modules:
                        import importlib
                        from core import sisi_booter
                        importlib.reload(sisi_booter)  # 重新加载模块
                    else:
                        from core import sisi_booter

                    if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                        sisi_core = sisi_booter.sisi_core
                        util.log(1, f"[NLP-SAFE] 方法2：从sisi_booter获取SmartSisi核心实例，ID: {id(sisi_core)}")
                except Exception as e:
                    util.log(2, f"[NLP-SAFE] 方法2失败: {str(e)}")
            
            # 方法3：从SmartSisi核心桥接获取静态变量
            if not sisi_core:
                try:
                    from llm.sisi_core_bridge import SisiCoreBridge
                    if SisiCoreBridge._sisi_core_instance:
                        sisi_core = SisiCoreBridge._sisi_core_instance
                        util.log(1, f"[NLP-SAFE] 方法3：从SmartSisi核心桥接静态变量获取，ID: {id(sisi_core)}")
                except Exception as e:
                    util.log(2, f"[NLP-SAFE] 方法3失败: {str(e)}")
            
            # 方法4：从sisi_booter获取（修复导入路径）
            if not sisi_core:
                try:
                    # 修复：直接导入sisi_booter，不是从core导入
                    from core import sisi_booter
                    if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                        sisi_core = sisi_booter.sisi_core
                        util.log(1, f"[NLP-SAFE] 方法4：从sisi_booter获取SmartSisi核心实例，ID: {id(sisi_core)}")
                except Exception as e:
                    util.log(2, f"[NLP-SAFE] 方法4失败: {str(e)}")

            # 最终状态记录
            if sisi_core:
                util.log(1, f"[NLP通知-SAFE] ✅ 成功获取SmartSisi核心实例，ID: {id(sisi_core)}")
            else:
                util.log(2, f"[NLP通知-SAFE] ❌ 所有方法都无法获取SmartSisi核心实例")

            # 获取要处理的通知列表
            if notifications_to_process is not None:
                # 使用传入的指定通知列表
                tool_notifications = notifications_to_process
                util.log(1, f"[NLP通知-SAFE] 处理{len(tool_notifications)}条指定通知")
            else:
                # 使用副本避免处理过程中的变化
                tool_notifications = list(transit.tool_notification_states)
                util.log(1, f"[NLP通知-SAFE] 处理队列中的所有通知({len(tool_notifications)}条)")

            if not tool_notifications:
                util.log(1, f"[NLP通知-SAFE] 没有通知需要处理")
                return True  # 没有通知也算成功处理

            # 通知去重 - 使用内容hash作为key
            processed_hashes = set()
            unique_notifications = []

            for notification in tool_notifications:
                # 计算通知内容的hash
                content = str(notification.get("content", ""))
                content_hash = hash(content)

                # 跳过重复内容
                if content_hash in processed_hashes:
                    util.log(1, f"[NLP通知-SAFE] 跳过重复内容通知 (hash: {content_hash})")
                    continue

                processed_hashes.add(content_hash)
                unique_notifications.append(notification)

            util.log(1, f"[NLP-SAFE] 发现{len(unique_notifications)}条不重复工具通知待处理")

            # 记录处理的所有通知内容，用于汇总日志
            processed_sources = []

            # 获取常规三阶段内容（用于引入历史上下文）
            optimized_contents = {}
            for phase in ["start", "middle", "final"]:
                states = transit.get_states_by_stage(phase)
                if states and len(states) > 0:
                    state_text = extract_text_from_state(states[0])
                    optimized_contents[phase] = state_text

            # 处理每条不重复的通知
            for notification in unique_notifications:
                # 跳过不需优化的通知
                if not notification.get("for_optimization", True):
                    continue

                content_type = notification.get("content_type", "text")
                # 🔥 修复：同时支持source和source_tool字段，优先使用source_tool，如果没有则使用source
                source_tool = notification.get("source_tool") or notification.get("source", "unknown_tool")
                content = notification.get("content", "") # 获取原始 content

                # --- 新增开始：处理音乐旁白通知 ---
                if content_type == "music_narration_result" and source_tool == "music_tool":
                    util.log(1, f"[NLP-SAFE] 检测到音乐旁白通知: 来自 {source_tool}")
                    
                    # content 此时应该是 music_tool 发送过来的字典
                    notification_content_data = content 
                    if not isinstance(notification_content_data, dict):
                        util.log(2, f"[NLP-SAFE] 音乐旁白通知内容格式错误，期望字典类型，收到: {type(notification_content_data)}")
                        continue

                    narration_text = notification_content_data.get("narration_text")
                    music_file_path = notification_content_data.get("music_file_path")

                    if not narration_text or not music_file_path:
                        util.log(2, f"[NLP-SAFE] 音乐旁白通知缺少旁白文本或音乐文件路径。旁白: {'有' if narration_text else '无'}, 文件路径: {'有' if music_file_path else '无'}")
                        continue
                    
                    # 验证音乐文件路径格式
                    if not os.path.isabs(music_file_path):
                        util.log(2, f"[NLP-SAFE] 音乐文件路径非绝对路径: {music_file_path}，可能导致播放失败")

                    util.log(1, f"[NLP-SAFE] 待优化旁白: {narration_text[:50]}... 音乐文件: {music_file_path}")

                    from utils import config_util
                    try:
                        config_util.load_config()
                        optimize_model = config_util.llm_optimize_model or "qwen-max-2025-01-25"
                    except Exception:
                        optimize_model = "qwen-max-2025-01-25"
                    
                    try:
                        narration_prompt = "请优化这段音乐旁白，使其更生动有趣，同时保持简洁自然："
                        optimized_narration = call_optimize_api(
                            narration_prompt,
                            narration_text,
                            optimize_model,
                            username="User",
                            phase="music_narration"
                        )
                        if not optimized_narration:
                            optimized_narration = narration_text
                    except Exception as e:
                        util.log(2, f"[NLP-SAFE] 优化音乐旁白异常: {str(e)}")
                        optimized_narration = narration_text

                    util.log(1, f"[NLP-SAFE] 优化后旁白: {optimized_narration[:50]}...")

                    # 🔥 修复：正确的音乐旁白发送逻辑
                    if sisi_core:
                        try:
                            music_playback_metadata = {
                                "phase": "notification",
                                "source_tool": source_tool,
                                "is_tool_notification": True,
                                "content_type": "music_narration_result",
                                "narration_text": optimized_narration,
                                "music_file_path": music_file_path,
                                "playback_order": ["narration", "music"]
                            }
                            # 直接使用优化后的旁白作为主要内容，SmartSisi核心会播放这个旁白
                            display_message = optimized_narration  # 这个会被播放作为旁白
                            
                            sisi_core.agent_callback(
                                display_message,
                                "normal",
                                is_intermediate=True,
                                metadata=music_playback_metadata
                            )
                            util.log(1, f"[NLP-SAFE] ✅ 已发送音乐旁白和文件路径到SmartSisi核心")
                        except Exception as callback_err:
                            util.log(2, f"[NLP-SAFE] SmartSisi核心回调音乐旁白通知异常: {str(callback_err)}")
                    else:
                        # 🔥 修复：当SmartSisi核心为空时，尝试直接使用桥接模块发送
                        try:
                            from llm.sisi_core_bridge import get_bridge
                            bridge = get_bridge()
                            
                            # 🔥 重要修复：不再检查is_core_active()，直接尝试发送
                            music_playback_metadata = {
                                "phase": "notification",
                                "source_tool": source_tool,
                                "is_tool_notification": True,
                                "content_type": "music_narration_result",
                                "narration_text": optimized_narration,
                                "music_file_path": music_file_path,
                                "playback_order": ["narration", "music"]
                            }
                            
                            # 使用桥接模块发送音乐旁白
                            result = bridge.send_notification(
                                optimized_narration,
                                source_tool,
                                is_intermediate=True,
                                metadata=music_playback_metadata
                            )
                            
                            if result:
                                util.log(1, f"[NLP-SAFE] ✅ 已通过SmartSisi核心桥接发送音乐旁白和文件路径")
                            else:
                                util.log(2, f"[NLP-SAFE] ❌ SmartSisi核心桥接发送音乐旁白失败")
                                # 🔥 添加fallback：直接尝试调用ESP32设备
                                try:
                                    from core import sisi_booter
                                    if hasattr(sisi_booter, 'notify_tts_event'):
                                        sisi_booter.notify_tts_event(optimized_narration, music_file_path)
                                        util.log(1, f"[NLP-SAFE] ✅ 使用fallback方式直接发送到ESP32设备")
                                except Exception as fallback_err:
                                    util.log(2, f"[NLP-SAFE] Fallback方式也失败: {str(fallback_err)}")
                        except Exception as bridge_err:
                            util.log(2, f"[NLP-SAFE] 使用SmartSisi核心桥接发送音乐旁白异常: {str(bridge_err)}")
                            util.log(2, f"[NLP-SAFE] 音乐旁白发送失败 - 旁白: {optimized_narration}, 文件: {music_file_path}")
                
                    processed_sources.append(source_tool) # 记录已处理
                    continue
                # --- 新增结束 ---

                # 跳过非文本通知 (原有的逻辑)
                # 如果上面的 music_narration_result 分支没有 continue，这个会执行
                if content_type != "text" and content_type != "event":
                    util.log(1, f"[NLP-SAFE] 跳过非文本/事件通知: 类型={content_type}, 来源={source_tool}")
                    continue

                # 确保 content 是字符串 (对于 text 和 event 类型)
                content_str = str(content)
                processed_sources.append(source_tool)

                if not content_str or len(content_str.strip()) < 5:
                    continue

                # 优化通知内容
                util.log(1, f"[NLP-SAFE] 优化{source_tool}工具通知: {str(content_str)[:50]}...")

                # 获取优化模型和配置
                from utils import config_util
                try:
                    config_util.load_config()
                    # 确保使用与三句话处理相同的配置获取方式
                    optimize_model = config_util.llm_optimize_model
                    util.log(1, f"[NLP-SAFE] 使用优化模型: {optimize_model}")
                except Exception as e:
                    # 如果获取失败，使用备用模型
                    optimize_model = "qwen-max-2025-01-25"  # 使用配置文件中指定的默认模型
                    util.log(2, f"[NLP-SAFE] 加载优化模型配置异常: {str(e)}，使用备用模型: {optimize_model}")

                # 调用优化API
                try:
                    tool_prompt = _get_tool_specific_prompt(source_tool, content_str, optimized_contents, None)
                    optimized = call_optimize_api(
                        tool_prompt,
                        content_str,
                        optimize_model,
                        username="User",
                        phase="notification"
                    )

                    if not optimized:
                        optimized = content_str
                except Exception as e:
                    util.log(2, f"[NLP-SAFE] 优化{source_tool}工具通知异常: {str(e)}")
                    optimized = content_str

                # 记录优化结果
                util.log(1, f"[NLP-SAFE] {source_tool}工具通知优化结果: {optimized[:50]}...")

                # 发送到SmartSisi核心
                if optimized:
                    try:
                        # 🔥 修复：优先使用已获取的SmartSisi核心实例
                        if not sisi_core:
                            util.log(2, f"[NLP-SAFE] SmartSisi核心未注册，尝试强制桥接发送")
                            # 尝试通过桥接模块强制发送
                            try:
                                from llm.sisi_core_bridge import get_bridge
                                bridge = get_bridge()
                                metadata = {
                                    "phase": "notification",
                                    "source_tool": source_tool,
                                    "is_tool_notification": True
                                }
                                result = bridge.send_notification(
                                    optimized,
                                    source_tool,
                                    is_intermediate=True,
                                    metadata=metadata
                                )
                                if result:
                                    util.log(1, f"[NLP-SAFE] ✅ 已通过桥接强制发送{source_tool}工具通知")
                                    continue
                                else:
                                    util.log(2, f"[NLP-SAFE] ❌ 桥接强制发送失败")
                            except Exception as bridge_err:
                                util.log(2, f"[NLP-SAFE] 桥接强制发送异常: {str(bridge_err)}")

                            util.log(2, f"[NLP-SAFE] 所有发送方式失败，保存通知到文件")
                            try:
                                # 保存通知到文件以便后续处理
                                notice_dir = os.path.join("resources", "optimized_notices")
                                os.makedirs(notice_dir, exist_ok=True)

                                # 构建保存数据
                                save_data = {
                                    "optimized_content": optimized,
                                    "source_tool": source_tool,
                                    "timestamp": time.time(),
                                    "metadata": {
                                        "phase": "notification",
                                        "source_tool": source_tool,
                                        "is_tool_notification": True
                                    }
                                }

                                # 生成文件名并保存
                                timestamp = int(time.time())
                                filepath = os.path.join(notice_dir, f"optimized_{source_tool}_{timestamp}.json")
                                with open(filepath, "w", encoding="utf-8") as f:
                                    json.dump(save_data, f, ensure_ascii=False, indent=2)

                                util.log(1, f"[NLP-SAFE] 已保存优化通知到文件: {filepath}")
                            except Exception as save_err:
                                util.log(2, f"[NLP-SAFE] 保存通知到文件失败: {str(save_err)}")
                            continue

                        metadata = {
                            "phase": "notification",
                            "source_tool": source_tool,
                            "is_tool_notification": True
                        }
                        sisi_core.agent_callback(
                            optimized,
                            "normal",
                            is_intermediate=True,
                            metadata=metadata
                        )
                        util.log(1, f"[NLP-SAFE] 已发送优化后的{source_tool}工具通知到SmartSisi核心")
                    except Exception as callback_err:
                        util.log(2, f"[NLP-SAFE] SmartSisi核心回调异常: {str(callback_err)}")
                        util.log(2, f"[NLP-SAFE] 通知优化结果(发送失败): {optimized}")

            # 清空已处理的通知
            processed_ids = [id(n) for n in tool_notifications]
            transit.tool_notification_states = [n for n in transit.tool_notification_states
                                              if id(n) not in processed_ids]

            util.log(1, f"[NLP-SAFE] 已处理{len(tool_notifications)}条工具通知，队列中剩余{len(transit.tool_notification_states)}条")
            return True

        except Exception as e:
            util.log(2, f"[NLP-SAFE] 处理工具通知异常: {str(e)}")
            import traceback
            util.log(2, f"[NLP-SAFE] 详细错误: {traceback.format_exc()}")
            return False

    # 替换为安全版本
    process_tool_notifications_with_transit = safe_process_tool_notifications_with_transit

    try:
        from sisi_memory.context_kernel import get_flag
        if get_flag("debug_tool_notifications", False):
            util.log(1, "[NLP] tool_notification_handler_installed")
    except Exception:
        pass

    return True

# 自动安装（导入期）
fix_tool_notifications_processing()
