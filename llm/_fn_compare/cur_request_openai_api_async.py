async def request_openai_api_async(text: str, uid=0, observation: str = ''):
    """
    寮傚鐞嗚姹傦紝鏀寔骞惰璋?

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

        # 鏌ュ伐鍏疯皟?
        if is_tool_call_quick(text):
            # 鍗曞伐鍏疯皟鐢肩洿鎺ュ鐞?
            tool_result = process_with_tools_sync(text, uid)
            if tool_result:
                return tool_result, "llm"

        # 鍒涘缓浼氳瘽骞舵瀯寤烘眰鏁?
        session = get_session()
        history_context = get_communication_history(uid, query_text=text, as_text=True)

        #  鏋勫缓鍖呭惈鍘嗗彶涓婁笅鏂囩殑鎻愮ず?
        if isinstance(history_context, str) and history_context.strip() and history_context not in ("无话历史", "无历史"):
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

        # 鍙?
        url = llm_cfg["base_url"] + "/chat/completions"
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f"Bearer {llm_cfg['api_key']}"
        }

        # 寮傚彂?
        async def async_request():
            # 璁剧疆瓒呮椂锛屼笌鍚岃肪淇濇寔?
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as client_session:
                async with client_session.post(url, json=data, headers=headers) as response:
                    if response.status == 200:
                        result = await response.json()

                        if "choices" not in result or not result["choices"]:
                            return "让我想想该怎么回答...", "gentle"

                        content = result["choices"][0]["message"]["content"]

                        # 杈撳嚭moji鐨凩LM杩斿洖鍐?
                        util.log(1, f"[LLM] 🤖 {content} 🤖")

                        # 鐩存帴澶勭悊鏂囨湰鍐?
                        text = content.strip()

                        # 改进前缀清理逻辑，处理更多可能的前缀情况
                        # 常见的错误前缀模式列表
                        prefix_patterns = [
                            "蕯ignment:", "alignment:", "瀵归綈:", "鍥炵瓟:", "鍥?", "assistant:",
                            "ai:", "response:", "绛?", "绛?"
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

                        # 濡傛灉鏂囨湰浠ヨ〃鎯呭彿寮€澶达紝涔熷皾璇曟竻?
                        if text and text[0] in ["🤫", "😐", "😠", "🤖"]:
                            text = text[1:].strip()

                        # 娴嬫儏缁硅缃浉搴斿弬鏁?
                        tone = "gentle"  # 默认温和语气

                        # 娴嬫劋鎬掓儏?
                        if "😠" in text:
                            tone = "angry"
                        # 检测悄悄话情绪
                        elif "🤫" in text:
                            tone = "whisper"

                        # 鍦ㄦ棩蹇椾腑鏍囨ā鍨嬫潵婧愶紝浣嗕笉淇敼瀹為檯鍥炲鍐?
                        log_text = f"[NLP-7B] {text}"
                        util.log(1, f"[LLM] 🤖 {log_text} 🤖")

                        return text, tone
                    else:
                        error_text = await response.text()
                        util.log(2, f"[LLM] API错误: 状态码 {response.status}, 错误信息: {error_text}")
                        return f"抱歉，API请求失败，状态码: {response.status}", "gentle"

        # 灏濊瘯瀵煎叆aiohttp锛屾灉鍏ュけ璐ュ垯浣跨敤鍚屾柟娉?
        try:
            import aiohttp
            return await async_request()
        except ImportError:
            util.log(2, "[LLM] aiohttp模块未安装，使用同步方法")
            # 浣跨敤鍚屾柟娉曪紝浣嗘坊鍔犺秴鏃舵帶鍒?
            with concurrent.futures.ThreadPoolExecutor() as executor:
                try:
                    # 娣诲姞瓒呮椂鎺у埗锛屾敼?0绉掔‘淇濇湁瓒崇殑鐞嗘椂?
                    future = executor.submit(send_llm_request, session, data, llm_cfg)
                    response_tuple = future.result(timeout=10)  # 澧炲姞瓒呮椂鏃堕棿?0?

                    if isinstance(response_tuple, tuple) and len(response_tuple) == 2:
                        return response_tuple
                    else:
                        # 纭胯繑鍥炲厓缁勬牸寮?
                        if isinstance(response_tuple, dict):
                            return response_tuple.get("text", "模型返回为空"), response_tuple.get("tone", "gentle")
                        elif isinstance(response_tuple, str):
                            return response_tuple, "gentle"
                        else:
                            return "抱歉，响应格式不正确", "gentle"
                except concurrent.futures.TimeoutError:
                    util.log(2, "[LLM] 请求超时")
                    return "请求超时，请稍后重试", "gentle"
        except Exception as e:
            util.log(2, f"[LLM] 异步请求失败: {str(e)}")
            return f"抱歉，请求处理失败: {str(e)}", "gentle"

    except Exception as e:
        import traceback
        error_msg = f"LLM模型异步处理异常: {str(e)}\n{traceback.format_exc()}"
        util.log(2, error_msg)
        return f"抱歉，处理您的请求时出现问题: {str(e)}", "gentle"
