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
