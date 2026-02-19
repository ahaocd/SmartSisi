def question(content, uid=0, observation="", audio_context=None, brain_prompts=None, speaker_info=None, mode_switched: bool = False):
    """鎻愰棶鏂规硶锛岀悊琛ㄦ儏骞惰幏鍙栧洖搴?

    Args:
        content: 鐢ㄦ埛杈撳叆鍐?
        uid: 用户ID
        observation: 观察信息
        audio_context: 闊充笂涓嬫枃鏁版嵓鏂?
        brain_prompts: 前脑系统生成的动态提示词（新增）
    Returns:
        Tuple[str, str]: (鍥炵瓟鏂囨湰, 璇熼鏍?
    """

    # 馃尶 娴嬫煶鍙惰皟鐢ㄩ渶姹傦紝浣嗕笉鍦ㄥ鐞嗗垏鎹?
    # 鏌冲彾鐩稿叧姹傚皢鐢辫矾鐢辩郴缁?
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, dict):
                if part.get("type") == "text":
                    text_parts.append(str(part.get("text") or "").strip())
                    continue
                text_parts.append(f"[{part.get('type') or 'part'}]")
            else:
                text_parts.append(str(part))
        content = " ".join([p for p in text_parts if p]).strip()
    elif isinstance(content, dict):
        if "text" in content:
            content = str(content.get("text") or "").strip()
        else:
            try:
                content = json.dumps(content, ensure_ascii=False)
            except Exception:
                content = str(content)
    else:
        content = str(content or "")
    liuye_keywords = ["叫柳叶", "柳叶", "医疗包", "系统诊断", "代码优化", "AI协作"]
    if any(word in content for word in liuye_keywords):
        util.log(1, f"[NLP] 检测到柳叶需求关键词，将路由到医疗包系统")
        # 杩欓噷搴旇皟鐢ㄨ窋绯荤粺锛屼笉鏄涙帴鍒囨崲妯?
        # TODO: 闆嗘垚鏌冲彾璺旂郴缁?
    util.log(1, f"[NLP] question函数输入: {content}")

    # === 鐪熺殑LLM娴佸紡锛圫SE锛夎緭鍑轰笌娈靛唴鍗虫椂TTS ===
    def _stream_llm_and_tts(messages: list, style_hint: str = "gentle") -> tuple:
        """璋冪敤OpenAI鍏糞SE娴佸紡锛岃竟鏀秚oken杈瑰垎娈靛苟TTS銆傝繑?瀹屾暣鏂囨湰, style)?

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
            # 馃敟 鍏抽敭锛氬湪try鍧楀唴濮嬪畾涔塻kip_flag_set
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
            # 寤虹珛娴佸紡璇锋眰锛堢敤鑷姩unicode瑙ｇ爜锛屽己鍒禪TF-8瑙ｆ瀽?
            resp = session.post(url, json=data, headers=headers, stream=True, timeout=(1, 30))
            # 馃敡 鍙嬪ソ閿欙細閴?鏉冮檺鍒忔姏寮傚父锛岀洿鎺ョ粰鍑哄彄浣滅殑鎻愮ず
            if resp.status_code in (401, 403):
                persona = get_current_system_mode()
                hint = (
                    f"AI接口认证失败(HTTP {resp.status_code})。"
                    f"请检查 SmartSisi/system.conf 中 {persona}_llm_api_key 和 {persona}_llm_base_url 配置。"
                )
                util.log(2, f"[NLP-Stream] {hint}")
                return "", style_hint

            try:
                resp.raise_for_status()
            except Exception as _http_e:
                # 灏介噺鎶婃湇鍔¤繑鍥炰綋鎵撳嚭鏉ワ紙鎴柤锛屾柟渚垮畾浣嶆槸妯″瀷?鍙傛暟/浠ｇ悊鐨勯棶?
                try:
                    body_preview = (resp.text or "")[:500]
                except Exception:
                    body_preview = ""
                util.log(2, f"[NLP-Stream] HTTP异常: {str(_http_e)}; body[:500]={body_preview}")
                raise

            # 鎾旂浉鍏?
            try:
                from core import sisi_booter
                sisi_core = getattr(sisi_booter, 'sisi_core', None) or getattr(sisi_booter, 'sisiCore', None)
            except Exception as e:
                sisi_core = None

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
                # 馃敟 锛氬彧鎸夋爣鐐瑰垎娈碉紝涓嶆寜鏃堕棿/闀垮害寮哄埗鍒嗭紝閬垮厤涓€鍙ヨ瘽琚嬫垚涓ゆ鑷存儏鎰熶笉?
                ready_by_punct = bool(seg_buf and re.search(r'[銆傦紒??锝瀪]$', seg_buf))
                # 鑻ュ寘鍚玡ffect锛屽敖閲忕瓑鍒板彸渚у彞鏈嗗悙锛屼互瀵归綈鎻掑叆?
                contains_effect = bool(re.search(r'\{([A-Za-z0-9_\u4e00-\u9fff]+)\}', seg_buf))
                if contains_effect and not force and not ready_by_punct:
                    return
                if (force or ready_by_punct) and seg_buf and brace_depth == 0:
                    # 按出现顺序处理{text,effect}序列
                    sequence = []
                    s = seg_buf
                    # 娓呯悊鐗规畩鎺у埗?
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
                            if sisi_core:
                                try:
                                    # 鏌冲彾妯″紡瑕佸垱寤哄甫interleaver鏍囪瘑鐨刬nteract瀵硅薄
                                    from llm.liusisi import get_current_system_mode
                                    current_mode = get_current_system_mode()
                                    if current_mode == "liuye":
                                        from core.interact import Interact
                                        interact_obj = Interact(interleaver="liuye", interact_type=2, data={"user": "User", "text": cleaned_text})
                                    else:
                                        interact_obj = None
                                    
                                    # 馃敟 鍏抽敭锛氫繚鎸佹祦寮廡TS鎾?
                                    sisi_core.process_audio_response(
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
                            # 甯х骇鎻掑叆锛氬皢鏁堟灉闊宠浆涓篛PUS甯у苟鐩存帴鍏ラ槦锛屼笉鏆傚仠?
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
                                        util.log(2, f"[NLP-Stream] 音频文件不存在: {fpath}")
                                        continue

                                    # PC璺撅細涓嶈璧皃ygame骞舵挃锛屾敼涓烘帓闃熶覆琛屾彃?
                                    if not _esp32_connected():
                                        ok = _enqueue_pc_audio(fpath, label=f"{ttype}:{payload}")
                                        if ok:
                                            emitted_any = True
                                            util.log(1, f"[NLP-Stream] PC队列插入音频: {payload}")
                                        else:
                                            util.log(2, f"[NLP-Stream] PC队列插入失败: {payload}")
                                        continue

                                    # ESP32璺撅細鎸夌被鍨嬭蛋澶囨彃?
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
                                    # 鍗虫椂瑙﹀彂绯荤粺鍒囨崲锛堜緥?{濡箎 / {鏌冲彾} ?
                                    try:
                                        et.detect_and_trigger_emotions("{" + payload + "}", is_ai_response=True)
                                        # 鍒囨崲涓嶄唬琛ㄦ湁闊虫拠锛屼笉鏍噀mitted_any
                                    except Exception as _se:
                                        util.log(2, f"[NLP-Stream] 系统切换触发失败: {_se}")
                            except Exception as _e:
                                util.log(2, f"[NLP-Stream] 帧级插入失败: {_e}")

                    # 鑻ユ湰娈靛彧鏈夋爣璁版棤姝ｆ枃锛屼篃瑕佹帹閫佸墠绔?
                    if not has_text_part and display_text.strip():
                        try:
                            if sisi_core and hasattr(sisi_core, "send_panel_reply"):
                                sisi_core.send_panel_reply(display_text, username="User", is_intermediate=True, phase="stream")
                        except Exception as _se:
                            util.log(2, f"[NLP-Stream] 仅前端显示失败: {_se}")

                    seg_buf = ""
                    last_emit = now

            # 寮哄埗鎸塙TF-8瑙ｆ瀽SSE
            chunk_count = 0  # 🔥 调试：统计收到的chunk数量
            music_status_sent = set()  # 馃幍 璁板綍宸插彂閫佺殑闊充箰鐘讹紝閬垮厤閲?
            # 馃敟 璋冭瘯锛氭墦鍗版眰鍙?
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
                        util.log(1, f"[NLP-Stream调试] 收到[DONE]，流式结束，已收到{chunk_count}个chunk，全文: {full_text}")
                        break
                    try:
                        obj = json.loads(payload)
                        delta = obj.get('choices', [{}])[0].get('delta', {})
                        token = delta.get('content', '')
                        # 馃敟 璋冭瘯锛氭墦鍗版瘡涓猚hunk鐨勫唴?
                        util.log(1, f"[NLP-Stream调试] 收到chunk: token长度={len(token) if token else 0}, token内容={'有内容' if token else '空'}")
                        # 馃敟 璋冭瘯锛歩nish_reason鍜寀sage
                        finish_reason = obj.get('choices', [{}])[0].get('finish_reason')
                        usage = obj.get('usage')
                        if finish_reason:
                            util.log(1, f"[NLP-Stream调试] finish_reason={finish_reason}, usage={usage}, 当前全文: {full_text}")
                    except Exception as e:
                        util.log(2, f"[NLP-Stream调试] JSON解析失败: {e}")
                        token = ""
                    if not token:
                        util.log(1, "[NLP-Stream调试] 跳过空token")
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
            # 鍚巉lush
            if seg_buf:
                try_emit(force=True)
            
            # 娴佸紡鎾旂粨鏉燂細宸叉挱鍑鸿繃鍐咃紝缃疯繃鏍囧織闃瞣re浜屾拪
            util.log(1, f"[NLP-Stream调试] 🚀 流式播报结束，emitted_any={emitted_any}, 全文长度={len(full_text)}, chunk数={chunk_count}")
            try:
                from core import sisi_booter
                target_core = getattr(sisi_booter, 'sisi_core', None) or getattr(sisi_booter, 'sisiCore', None)
                if target_core:
                    # 馃敟 鍏抽敭锛氭祦寮忕粨鏉熷悗鎵嶇椒杩囨爣蹇楋紝閬垮厤鍚庣画鍒員TS璺宠繃
                    if emitted_any and not skip_flag_set[0]:
                        setattr(target_core, '_skip_next_tts', True)
                        setattr(target_core, '_skip_tts_timestamp', time.time())
                        skip_flag_set[0] = True
                        util.log(1, "[NLP-Stream] 已在流式结束后设置_skip_next_tts，防止Core二次播报")
                    else:
                        util.log(1, "[NLP-Stream] 跳过设置标志（未播出或已设置）")
            except Exception as _e:
                util.log(2, f"[NLP-Stream] 标志处理失败: {_e}")
            return full_text.strip(), style_hint
        except Exception as e:
            util.log(2, f"[NLP-Stream] 流式SSE异常: {e}")
            # 杩斿洖绌烘枃鏈讳究涓婂眰璧伴潪娴佸紡鍏?
            return "", style_hint

    try:
        # 馃幆 鏂帮細闊抽涓婁笅鏂囧鐞?
        audio_context_prompt = ""
        if audio_context:
            try:
                from .audio_context_processor import get_audio_context_processor
                from .audio_context_llm import get_audio_context_llm

                # 澶勭悊闊充笂涓?
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

                # 鍚婂悗鍙板垎鏋愮嚎绋?
                threading.Thread(target=background_analysis, daemon=True).start()

                # 馃幆 鐢熸垚鍗虫椂涓婁笅鏂囨彁绀鸿瘝锛堜笉闃?
                context_prompt = audio_processor.get_context_prompt(audio_context)
                if context_prompt:
                    audio_context_prompt = f"\n{context_prompt}\n"
                    util.log(1, f"[音频上下文] 生成提示: {context_prompt[:50]}...")

            except Exception as e:
                util.log(2, f"[音频上下文] 处理失败: {e}")
                audio_context_prompt = ""
        # 鏄愪娇鐢ㄦ祦寮忔ā寮?- 鍚斿垎鍧楁祦寮?
        use_stream = True

        # 预置情感标记，避免后续未赋值时报错
        emotion = ""

        # 鏌ユ槸鍚﹀寘鍚嗙姧璇?
        disrespectful_keywords = [
            "????", "???", "??", "??", "??",
            "??", "?", "??", "??", "??", "??", "??", "??", "??", "??"
        ]

        is_disrespectful = any(keyword in content.lower() for keyword in disrespectful_keywords)

        # 鏌ユ槸鍚﹀寘鍚夋畩姘旀寚?
        whisper_keywords = ["悄悄", "小声", "偷偷", "轻声"]
        fast_keywords = ["???", "???", "?", "??"]
        slow_keywords = ["???", "???", "??"]

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

        # 鍔ㄨ幏鍙栧綋鍓嶇敤鎴疯韩?
        current_user_name = "用户"
        current_user_role = "guest"
        if speaker_info:
            current_user_name = speaker_info.get('real_name', '用户')
            current_user_role = speaker_info.get('role', 'guest')

        #  闀挎湡璁板繂娉ㄥ叆锛堝欢杩熸敞鍏ョ増?
        # 绾︽潫锛氬墠?question() 涓嶅厑璁稿疄?鍗婂悓姝?Mem0?
        # 璁板繂?+ 缁勭粐鐢卞墠?鍔ㄤ腑鏋㈠悗鍙颁骇鍑猴紝涓嬩竴杞氳繃 brain_prompts['memory_context'] 娉ㄥ叆?
        memory_context_prompt = ""
        try:
            if brain_prompts:
                mem_ctx = (brain_prompts.get("memory_context") or "").strip()
                if mem_ctx and mem_ctx not in ("?????", "???Sisi??", "???????"):
                    memory_context_prompt = mem_ctx
        except Exception:
            memory_context_prompt = ""
        base_prompt = build_prompt(observation, "")

        dynamic_parts = []
        if audio_context_prompt:
            dynamic_parts.append(audio_context_prompt.strip())
        dynamic_block = "\n".join([p for p in dynamic_parts if p]).strip()

        # 鏋勫缓鐢ㄦ埛娑堟伅锛屼娇鐢ㄥ姩鎬佽韩浠戒俊?
        if speaker_info and speaker_info.get('real_name'):
            speaker_name = speaker_info['real_name']
            user_message = content
        else:
            user_message = content

        # 不再在用户消息中注入时间戳，避免模型复读

        # 缁?system messages锛堥噸瑕佸湪鍓嶏紝鍙傚湪鍚庯級
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

        # Debug: dump full payload sent to LLM
        util.log(1, "[NLP-FULL-DEBUG] ==================== START ====================")
        try:
            from sisi_memory.chat_history import format_messages_as_text
            recent_text = format_messages_as_text(recent_messages or [])
        except Exception:
            recent_text = ""
        system_blob = "\n\n".join([m.get("content", "") for m in system_messages]).strip()
        util.log(1, f"[NLP-FULL-DEBUG] System Prompt (first 500):\n{system_blob[:500]}")
        util.log(1, f"[NLP-FULL-DEBUG] System Prompt (last 500):\n{system_blob[-500:]}")
        util.log(1, f"[NLP-FULL-DEBUG] System Prompt length: {len(system_blob)} chars")
        util.log(1, f"[NLP-FULL-DEBUG] User Message: {user_message}")
        util.log(1, "[NLP-FULL-DEBUG] Recent Context:\n" + (recent_text[:500] if recent_text else "(empty)"))
        util.log(1, "[NLP-FULL-DEBUG] Brain Context:\n" + (brain_context[:300] if brain_context else "(empty)"))
        util.log(1, "[NLP-FULL-DEBUG] ==================== END ====================")

        llm_cfg = get_llm_cfg()

        # === 涓昏矾寰勶細鐪烲LM娴佸紡 ===
        if use_stream:
            streamed_text, style_stream = _stream_llm_and_tts(messages, style_hint="gentle")
            if streamed_text:
                # 瀛樺偍涓庤繑?
                answer = streamed_text
                style = style_stream
            else:
                # 娴佸紡澶辫触锛氫笉鍋氬厹搴曪紝涓嶈繘琛岄潪娴佸紡鍥?
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

        # === 鎯呮劅/绯荤粺鍒囨崲鏍囧鐞?===
        # 娴佸紡妯″紡宸插湪 _stream_llm_and_tts 涓у彂杩囨儏鎰燂紝杩欓噷涓嶉噸瑙﹀彂?
        # 闈炴祦寮忔ā寮忛渶瑕佽Е鍙戜竴娆★紝浣嗕笉娓呯悊鏂囨湰锛堜繚鐣欑粰鍓?鍘嗗彶锛?
        try:
            if not use_stream:
                from utils.emotion_trigger import detect_and_trigger_emotions
                detect_and_trigger_emotions(answer or "", is_ai_response=True)
                util.log(1, "[NLP-LLM] 已执行非流式情感触发")
            else:
                util.log(1, "[NLP-LLM] 流式模式已在上游触发情感")
        except Exception as _e:
            util.log(2, f"[NLP-LLM] 情感触发解析失败: {_e}")

        if not (answer or "").strip():
            util.log(2, "[NLP-LLM] empty_model_output (no fallback)")
            return "", style

        #  寮傚瓨鍌ㄥ璇濆埌蹇嗙郴?- add_sisi_interaction_memory宸茬粡鏄兼鐨?
        try:
            # 缁熶竴 user_id 瑙勫垯锛氫笌鍘嗗彶 SoT ?uid鈫抲ser_id 瑙勫垯鑷达紝骞跺熀?mode 鍛藉悕绌洪棿闅?
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

            # 馃殌 鐩存帴璋冪敤寮傚瓨鍌ㄥ嚱鏁帮紙鍐呴儴宸茬粡鏄悗鍙扮嚎绋?
            success = add_sisi_interaction_memory(
                text=content,  # 鐢ㄦ埛璇寸殑?
                speaker_id=namespaced_user_id,  # 命名空间化的用户ID
                response=answer,  # 鏌崇殑鍥?
                speaker_info=speaker_info  # 澹扮汗韬讳俊鎭?
            )
            util.log(1, f"[NLP-LLM] 🚀 记忆存储已提交: {namespaced_user_id}")
        except Exception as e:
            util.log(2, f"[NLP-LLM] 记忆存储异常: {e}")

        # 瀵硅瘽浜嬩欢?SoT 鐨勫啓鍏ョ敱 core/sisi_core.py 缁熶竴璐熻矗锛岃繖閲屼笉閲嶅啓鍏ワ紝閬垮厤鍙?閲嶈褰?

        #  瀵硅瘽鍘嗗彶宸茶繃鈥滀簨浠舵祦 + 鎽?+ 璁板繂鈥濈粺绠＄悊锛屾棤鎵嬪姩缁存姢history鍒楄〃

        # 鍙滄湁琛ㄦ儏鏃舵坊鍔犺〃鎯?
        return f"{emotion} {answer}" if emotion else answer, style

    except Exception as e:
        import traceback
        error_detail = traceback.format_exc()
        util.log(2, f"[NLP] question函数异常: {e}")
        util.log(2, f"[NLP] 详细错误: {error_detail}")

        answer = f"系统遇到了一点问题: {str(e)}"
        style = 'gentle'
        util.log(1, f"[NLP] question函数输出文本: {answer}")
        util.log(1, f"[NLP] question函数输出tone: {style}")
        return answer, style
