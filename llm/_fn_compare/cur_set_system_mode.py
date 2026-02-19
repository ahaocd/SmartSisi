def set_system_mode(mode):
    """设置系统模式"""
    global current_system_mode, _mode_switch_pending
    if mode in ["sisi", "liuye"]:
        if mode != current_system_mode:
            _mode_switch_pending = True
        current_system_mode = mode
        util.log(1, f"[NLP] 系统模式切换: {mode}")

        # 馃敡 閲嶏細鍒囨崲绯荤粺鏃舵竻鐞嗙姸?
        try:
            from core import sisi_booter
            if hasattr(sisi_booter, 'sisi_core') and sisi_booter.sisi_core:
                # 閲嶇疆chatting鍜宻peaking鐘?
                sisi_booter.sisi_core.chatting = False
                sisi_booter.sisi_core.speaking = False
                util.log(1, "[NLP] 系统切换时已清理状态: chatting=False, speaking=False")
        except Exception as e:
            util.log(2, f"[NLP] 清理状态失败: {e}")

        # 馃摙 閫氱煡鍓嶇郴缁熷垏鎹簨浠讹紙鐢ㄤ簬GUI鍚?
        # Root fix: unify voice policy application for all mode switch paths.
        try:
            from utils.voice_policy import apply_voice_for_mode
            apply_voice_for_mode(mode)
        except Exception as e:
            util.log(2, f"[NLP] voice policy apply failed: {e}")

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

        # 濡傛灉鍒囨崲鍒版煶鍙舵ā寮忥紝鍚婃煶鍙剁郴缁?
        if mode == "liuye":
            try:
                # 鏌冲彾绯荤粺鍚婇€昏緫宸插湪璺旂悊锛岃繖閲屽綍鏃?
                util.log(1, "[NLP] 柳叶系统模式已激活")

            except Exception as e:
                util.log(2, f"[NLP] 启动柳叶系统失败: {e}")

        # 如果切换回思思模式，关闭柳叶系统
        elif mode == "sisi":
            try:
                # 思思系统恢复逻辑
                util.log(1, "[NLP] 思思系统模式已恢复")
                # 涓嶉渶瑕佸鐨勫垏鎹㈤€昏緫锛屾ā寮忓凡缁忕疆?
            except Exception as e:
                util.log(2, f"[NLP] 关闭柳叶系统失败: {e}")
    else:
        util.log(2, f"[NLP] 无效的系统模式: {mode}")
