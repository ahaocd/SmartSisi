function normalizeHttpBase(base) {
  return String(base || "").trim();
}

function withDefaults(payload, defaults) {
  return { ...(defaults || {}), ...(payload || {}) };
}

export function getApiConsoleActions({ api, httpBase, payloads = {} } = {}) {
  const base = normalizeHttpBase(httpBase);
  const chatPayload = withDefaults(payloads.chat, {
    model: "sisi",
    messages: [{ role: "user", content: "ping" }],
    stream: false
  });

  const submitPayload = withDefaults(payloads.submit, { source: { ASR_mode: "funasr" } });
  const sendPayload = withDefaults(payloads.send, { username: "User", msg: "ping" });
  const getMsgPayload = withDefaults(payloads.get_msg, { username: "User" });
  const adoptMsgPayload = withDefaults(payloads.adopt_msg, { id: 1 });
  const greetPayload = withDefaults(payloads.to_greet, { username: "User", observation: "" });
  const stopTalkingPayload = withDefaults(payloads.to_stop_talking, { text: "测试打断" });
  const transparentPayload = withDefaults(payloads.transparent_pass, { user: "User", text: "ping", audio: "" });

  return [
    {
      id: "get-data",
      title: "/api/get-data",
      desc: "获取配置",
      run: () => api.apiGetData(base)
    },
    {
      id: "submit",
      title: "/api/submit",
      desc: "保存配置",
      run: () => api.apiSubmit(base, submitPayload)
    },
    {
      id: "start-live",
      title: "/api/start-live",
      desc: "启动实时音频",
      run: () => api.apiStartLive(base)
    },
    {
      id: "stop-live",
      title: "/api/stop-live",
      desc: "停止实时音频",
      run: () => api.apiStopLive(base)
    },
    {
      id: "get-run-status",
      title: "/api/get_run_status",
      desc: "运行状态",
      run: () => api.apiGetRunStatus(base)
    },
    {
      id: "send",
      title: "/api/send",
      desc: "发送文本",
      run: () => api.apiSendText(base, sendPayload)
    },
    {
      id: "to-wake",
      title: "/to_wake",
      desc: "唤醒",
      run: () => api.apiToWake(base)
    },
    {
      id: "to-stop-talking",
      title: "/to_stop_talking",
      desc: "打断",
      run: () => api.apiToStopTalking(base, stopTalkingPayload)
    },
    {
      id: "get-member-list",
      title: "/api/get-member-list",
      desc: "成员列表",
      run: () => api.apiGetMemberList(base)
    },
    {
      id: "browser-check",
      title: "/api/browser-check",
      desc: "浏览器兼容检查",
      run: () => api.apiBrowserCheck(base)
    },
    {
      id: "models",
      title: "/v1/models",
      desc: "模型列表",
      run: () => api.apiGetModels(base)
    },
    {
      id: "chat",
      title: "/v1/chat/completions",
      desc: "OpenAI 兼容聊天",
      run: () => api.apiChatCompletions(base, chatPayload)
    },
    {
      id: "chat-proxy",
      title: "/api/send/v1/chat/completions",
      desc: "OpenAI 兼容聊天（代理路径）",
      run: () => api.apiChatCompletions(base, chatPayload, { useProxyPath: true })
    },
    {
      id: "get-msg",
      title: "/api/get-msg",
      desc: "历史消息",
      run: () => api.apiGetMsg(base, getMsgPayload)
    },
    {
      id: "adopt-msg",
      title: "/api/adopt_msg",
      desc: "采纳消息",
      run: () => api.apiAdoptMsg(base, adoptMsgPayload)
    },
    {
      id: "to-greet",
      title: "/to_greet",
      desc: "打招呼",
      run: () => api.apiToGreet(base, greetPayload)
    },
    {
      id: "transparent-pass",
      title: "/transparent_pass",
      desc: "透传播放",
      run: () => api.apiTransparentPass(base, transparentPayload)
    }
  ];
}
