import { useSystemStore } from "../stores/systemStore";

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

function planStages({ msg, ttsAllowed }) {
  const lower = String(msg || "").toLowerCase();
  const wantsVoice = lower.includes("/voice") || lower.includes("/stt");
  const wantsAgent = lower.includes("/agent");
  const wantsTool = lower.includes("/tool");
  const wantsGuild = lower.includes("/guild");
  const wantsMcp = lower.includes("/mcp") || wantsTool;
  const wantsSkills = lower.includes("/skills") || lower.includes("/skill");

  const stages = [];
  if (wantsVoice) stages.push({ key: "stt", label: "ASR" });
  stages.push({ key: "llm", label: "LLM" });
  if (wantsAgent) stages.push({ key: "agent", label: "Agent" });
  if (wantsTool) stages.push({ key: "tool", label: "Tool" });
  if (wantsGuild) stages.push({ key: "guild", label: "Guild" });
  if (wantsMcp) stages.push({ key: "mcp", label: "MCP" });
  if (wantsSkills) stages.push({ key: "skills", label: "Skills" });
  stages.push({ key: "tts", label: ttsAllowed ? "TTS" : "TTS(拦截)", outcome: ttsAllowed ? "done" : "error" });

  return stages;
}

function schedulePipeline({ systemStore, system_id, traceId, stages, onDone }) {
  const baseDelays = {
    stt: 320,
    llm: 760,
    agent: 520,
    tool: 560,
    guild: 560,
    mcp: 520,
    skills: 420,
    tts: 520
  };

  let idx = 0;

  const tick = () => {
    const stage = stages[idx];
    if (!stage) return onDone?.();

    const key = stage.key;
    const outcome = stage.outcome || "done";

    if (key === "stt") systemStore.setAgentStatus(system_id, "listening");
    if (["llm", "agent", "tool", "guild", "mcp", "skills"].includes(key)) systemStore.setAgentStatus(system_id, "thinking");
    if (key === "tts" && outcome === "done") systemStore.setAgentStatus(system_id, "speaking");

    systemStore.setTraceStageState({ traceId, stageKey: key, state: "running" });

    const runMs = baseDelays[key] || 420;
    setTimeout(() => {
      systemStore.setTraceStageState({ traceId, stageKey: key, state: outcome === "error" ? "error" : "done" });
      idx += 1;
      setTimeout(tick, 120);
    }, runMs);
  };

  setTimeout(tick, 160);
}

export async function mockSendMessage({ system_id, username, msg }) {
  const systemStore = useSystemStore();

  systemStore.addMessage({ system_id, role: "user", content: msg, meta: { username } });

  const ttsAllowed = systemStore.activeAudioSystemId === system_id;
  const stages = planStages({ msg, ttsAllowed });

  const assistantMessageId = systemStore.addMessage({
    system_id,
    role: "assistant",
    content: "处理中…",
    meta: { username }
  });

  const traceId = systemStore.createTrace({ system_id, messageId: assistantMessageId, stages });
  systemStore.updateMessage({ system_id, id: assistantMessageId, patch: { meta: { trace_id: traceId } } });

  schedulePipeline({
    systemStore,
    system_id,
    traceId,
    stages,
    onDone: async () => {
      await sleep(160 + Math.random() * 220);
      const tail = ttsAllowed ? "" : "\n\n（提示）TTS 被仲裁拦截：只有“音频 active”的系统才能真正发声。";
      systemStore.updateMessage({
        system_id,
        id: assistantMessageId,
        patch: { content: `收到（${system_id}）：\n\n${msg}${tail}` }
      });
      systemStore.setAgentStatus(system_id, "idle");
    }
  });

  return { ok: true };
}

