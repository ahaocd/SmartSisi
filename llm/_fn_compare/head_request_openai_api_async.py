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
