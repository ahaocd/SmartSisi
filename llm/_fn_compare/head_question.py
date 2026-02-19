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
