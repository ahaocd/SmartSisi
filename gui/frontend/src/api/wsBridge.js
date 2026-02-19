import { useConfigStore } from "../stores/configStore";
import { useBackendStore } from "../stores/backendStore";
import { useEventStore } from "../stores/eventStore";
import { useSystemStore } from "../stores/systemStore";
import { collectUnknownKeys } from "./wsUtils";

function safeJsonParse(s) {
  try {
    return JSON.parse(s);
  } catch {
    return null;
  }
}

function normalizeWsUrl(url) {
  const u = String(url || "").trim();
  if (!u) return "";
  return u;
}

let shakeTimer = null;
function triggerUiShake() {
  if (typeof document === "undefined") return;
  const body = document.body;
  if (!body) return;
  body.classList.remove("ui-flash");
  // force reflow to restart animation
  void body.offsetWidth;
  body.classList.add("ui-flash");
  if (shakeTimer) clearTimeout(shakeTimer);
  shakeTimer = setTimeout(() => {
    body.classList.remove("ui-flash");
  }, 360);
}

function normalizeReplyContent(content) {
  if (typeof content === "string") return content;
  if (content == null) return "";
  try {
    return JSON.stringify(content);
  } catch {
    return String(content);
  }
}

function normalizeReplyAttachments(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const raw of list) {
    if (!raw || typeof raw !== "object") continue;
    const preview = String(raw.preview_url || "").trim();
    const id = String(raw.id || "").trim();
    if (!id && !preview) continue;
    out.push({
      id: id || `att_${Date.now()}_${Math.random().toString(16).slice(2)}`,
      kind: String(raw.kind || "file").trim(),
      name: String(raw.name || "attachment").trim(),
      mime: String(raw.mime || "application/octet-stream").trim(),
      size: Number(raw.size || 0) || 0,
      preview_url: preview,
      download_url: String(raw.download_url || preview || "").trim(),
      thumbnail_url: String(raw.thumbnail_url || "").trim(),
      duration_ms: Number(raw.duration_ms || 0) || 0,
      source: String(raw.source || "tool").trim()
    });
  }
  return out;
}

function normalizeStreamingChunk(text) {
  const s = String(text || "");
  return s.replaceAll("\r\n", "\n").replaceAll("\r", "\n").replace(/\n+/g, " ").replace(/[ \t]+/g, " ");
}

function normalizeForCompare(text) {
  return normalizeStreamingChunk(text).trim();
}

function isRecent(ms, windowMs) {
  if (!ms || !Number.isFinite(ms)) return false;
  return Date.now() - ms <= windowMs;
}

function joinChunk(before, chunk) {
  const b = String(before || "");
  const c = String(chunk || "");
  if (!b) return c;
  if (!c) return b;
  const last = b[b.length - 1] || "";
  const first = c[0] || "";
  if (/[A-Za-z0-9]$/.test(last) && /^[A-Za-z0-9]/.test(first)) return `${b} ${c}`;
  return `${b}${c}`;
}

function mergeAssistantText(before, chunk) {
  const prev = normalizeStreamingChunk(before);
  const next = normalizeStreamingChunk(chunk);
  if (!prev) return next;
  if (!next) return prev;
  if (next === prev) return prev;
  if (next.startsWith(prev)) return next;
  return joinChunk(prev, next);
}

function resolveReplySystemId(panelReply, fallbackSystemId) {
  const t = String(panelReply?.type || "").toLowerCase();
  if (t === "liuye") return "liuye";
  if (t === "sisi") return "sisi";
  return fallbackSystemId;
}

function resolveReplyRole(panelReply) {
  const t = String(panelReply?.type || "").toLowerCase();
  return t === "member" ? "user" : "assistant";
}

function patchAssistantPlaceholder(systemStore, systemId, content, metaPatch, open = false, attachments = null) {
  const list = systemStore.messagesBySystem[systemId] || [];
  const last = list[list.length - 1];
  if (!last || last.role !== "assistant") return false;
  if (!last.meta?.pending_reply) return false;
  const nextAttachments = Array.isArray(attachments) && attachments.length ? attachments : (last.attachments || []);
  systemStore.updateMessage({
    system_id: systemId,
    id: last.id,
    patch: {
      content,
      attachments: nextAttachments,
      meta: { ...(last.meta || {}), ...(metaPatch || {}), pending_reply: false, stream_open: !!open }
    }
  });
  return true;
}

function isDuplicateUserTail(systemStore, systemId, content) {
  const list = systemStore.messagesBySystem[systemId] || [];
  const last = list[list.length - 1];
  if (!last || last.role !== "user") return false;
  return String(last.content || "").trim() === String(content || "").trim();
}

function findLastUserMessage(systemStore, systemId) {
  const list = systemStore.messagesBySystem[systemId] || [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const m = list[i];
    if (m?.role === "user") return m;
  }
  return null;
}

function parseCreatedAt(msg) {
  if (!msg?.created_at) return NaN;
  const t = Date.parse(msg.created_at);
  return Number.isNaN(t) ? NaN : t;
}

function findAssistantAfterLastUser(systemStore, systemId) {
  const list = systemStore.messagesBySystem[systemId] || [];
  let lastUserIdx = -1;
  for (let i = list.length - 1; i >= 0; i -= 1) {
    if (list[i]?.role === "user") {
      lastUserIdx = i;
      break;
    }
  }
  for (let i = list.length - 1; i > lastUserIdx; i -= 1) {
    const m = list[i];
    if (m?.role === "assistant") return m;
  }
  return null;
}

function findAssistantByBackendId(systemStore, systemId, backendId) {
  if (!backendId) return null;
  const list = systemStore.messagesBySystem[systemId] || [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const m = list[i];
    if (m?.role !== "assistant") continue;
    if (m?.meta?.backend_msg_id === backendId) return m;
  }
  return null;
}

function findMessageById(systemStore, systemId, messageId) {
  if (!messageId) return null;
  const list = systemStore.messagesBySystem[systemId] || [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    if (list[i]?.id === messageId) return list[i];
  }
  return null;
}

function findAssistantStreamTail(systemStore, systemId) {
  const list = systemStore.messagesBySystem[systemId] || [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const m = list[i];
    if (m?.role !== "assistant") continue;
    if (m?.meta?.stream_open) return m;
    return null;
  }
  return null;
}

function appendAssistantChunk(systemStore, systemId, chunk, metaPatch = {}, { open = true, normalize = true } = {}) {
  const c = normalize ? normalizeStreamingChunk(chunk) : String(chunk || "");
  if (!c) return false;

  const tail = findAssistantStreamTail(systemStore, systemId);
  if (!tail) return false;

  const before = String(tail.content || "");
  const next = joinChunk(before, c);
  systemStore.updateMessage({
    system_id: systemId,
    id: tail.id,
    patch: { content: next, meta: { ...(metaPatch || {}), stream_open: !!open } }
  });
  return true;
}

function hasAnyKeyword(text, keywords) {
  const source = String(text || "");
  if (!source) return false;
  for (const key of keywords) {
    if (source.includes(key)) return true;
  }
  return false;
}

function updateStatusFromPanelMsg(systemStore, systemId, panelMsg, backendStore) {
  const m = String(panelMsg || "");
  if (!m) return;
  if (backendStore?.audioPlaying) return;

  const lower = m.toLowerCase();
  if (
    hasAnyKeyword(lower, ["thinking", "reason", "reasoning"]) ||
    hasAnyKeyword(m, ["\u601d\u8003", "\u63a8\u7406", "\u5206\u6790"])
  ) {
    systemStore.setAgentStatus(systemId, "thinking");
    return;
  }

  if (
    hasAnyKeyword(lower, ["listening", "wake", "wakeword"]) ||
    hasAnyKeyword(m, ["\u8046\u542c", "\u76d1\u542c", "\u5524\u9192"])
  ) {
    systemStore.setAgentStatus(systemId, "listening");
    return;
  }

  if (
    hasAnyKeyword(lower, ["speaking", "tts", "voice"]) ||
    hasAnyKeyword(m, ["\u8bf4\u8bdd", "\u64ad\u62a5", "\u5408\u6210"])
  ) {
    systemStore.setAgentStatus(systemId, "speaking");
  }
}

function setSpeakingFromAudio(systemStore, backendStore, playing) {
  // Step 1: disable frontend back-write for agent_status.
  // Agent state must come from backend explicit events only.
  void systemStore;
  void backendStore;
  void playing;
}

function emitControlIntentEvent(payload) {
  if (typeof window === "undefined") return;
  try {
    window.dispatchEvent(new CustomEvent("smartsisi:control-intent", { detail: payload || {} }));
  } catch {}
}

const KNOWN_WS_KEYS = [
  "deviceList",
  "voiceList",
  "liveState",
  "is_connect",
  "isConnect",
  "agent_status",
  "agentStatus",
  "panelMsg",
  "panelReply",
  "systemSwitch",
  "audio_status",
  "audioStatus",
  "audio_level",
  "audioLevel",
  "audio_event",
  "audioEvent",
  "audio_command",
  "audioCommand",
  "music_event",
  "musicEvent",
  "music_info",
  "musicInfo",
  "music_file",
  "musicFile",
  "music_title",
  "musicTitle",
  "control_intent",
  "controlIntent",
  "type"
];

export function startWsBridge(pinia) {
  const configStore = useConfigStore(pinia);
  const backendStore = useBackendStore(pinia);
  const eventStore = useEventStore(pinia);
  const systemStore = useSystemStore(pinia);

  let ws = null;
  let currentUrl = "";
  let manualClose = false;
  let reconnectTimer = null;
  let audioStopTimer = null;
  let lastAudioSignalAt = 0;
  const AUDIO_STOP_HOLD_MS = 860;
  const AUDIO_LEVEL_KEEP_MS = 1100;

  function push(kind, level, title, message, payload = {}) {
    eventStore.pushEvent({
      system_id: systemStore.currentSystemId,
      kind,
      level,
      title,
      message,
      payload
    });
  }

  function clearReconnect() {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    reconnectTimer = null;
  }

  function clearAudioStopTimer() {
    if (audioStopTimer) clearTimeout(audioStopTimer);
    audioStopTimer = null;
  }

  function noteAudioSignal(level = 0) {
    const n = Number(level);
    if (!Number.isFinite(n)) return;
    if (n <= 0.01) return;
    // Step 1: audio_level is telemetry only.
    // Legacy inference from level -> speaking is intentionally disabled.
  }

  function setAudioPlayingStable(playing, immediate = false) {
    const next = !!playing;
    if (next) {
      lastAudioSignalAt = Date.now();
      clearAudioStopTimer();
      backendStore.setAudioPlaying(true);
      return;
    }
    if (immediate) {
      clearAudioStopTimer();
      backendStore.setAudioPlaying(false);
      return;
    }
    const sinceAudioSignal = Date.now() - lastAudioSignalAt;
    if (sinceAudioSignal >= 0 && sinceAudioSignal < AUDIO_LEVEL_KEEP_MS) {
      clearAudioStopTimer();
      const wait = Math.max(120, AUDIO_LEVEL_KEEP_MS - sinceAudioSignal + 40);
      audioStopTimer = setTimeout(() => {
        audioStopTimer = null;
        setAudioPlayingStable(false);
      }, wait);
      return;
    }
    clearAudioStopTimer();
    audioStopTimer = setTimeout(() => {
      audioStopTimer = null;
      backendStore.setAudioPlaying(false);
    }, AUDIO_STOP_HOLD_MS);
  }

  function clearTransientUiState() {
    lastAudioSignalAt = 0;
    setAudioPlayingStable(false, true);
    backendStore.setMusicState(false, null);
    systemStore.clearStreamingFlags();
  }

  function disconnect() {
    manualClose = true;
    clearReconnect();
    clearAudioStopTimer();
    try {
      ws?.close?.();
    } catch {}
    ws = null;
    currentUrl = "";
    clearTransientUiState();
    backendStore.setWsConnected(false, "");
  }

  function scheduleReconnect() {
    clearReconnect();
    if (manualClose) return;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      refresh();
    }, 1200);
  }

  function connect(url) {
    const u = normalizeWsUrl(url);
    if (!u) return;
    if (ws && currentUrl === u) return;
    disconnect();

    manualClose = false;
    currentUrl = u;
    try {
      ws = new WebSocket(u);
    } catch (e) {
      push("debug", "error", "WS connect failed", String(e?.message || e));
      scheduleReconnect();
      return;
    }

    ws.onopen = () => {
      backendStore.setWsConnected(true, u);
      push("status", "success", "WS connected", u);
    };

    ws.onclose = () => {
      clearTransientUiState();
      backendStore.setWsConnected(false, u);
      push("status", "warning", "WS disconnected", u);
      scheduleReconnect();
    };

    ws.onerror = () => {
      clearTransientUiState();
      backendStore.setWsConnected(false, u);
      scheduleReconnect();
    };

    ws.onmessage = (ev) => {
      backendStore.onMessage();
      const obj = typeof ev?.data === "string" ? safeJsonParse(ev.data) : null;
      if (!obj || typeof obj !== "object") return;

      const unknownKeys = collectUnknownKeys(obj, KNOWN_WS_KEYS);
      if (unknownKeys.length) {
        push("debug", "info", "WS unknown keys", `keys: ${unknownKeys.join(", ")}`, { keys: unknownKeys, payload: obj });
      }

      if (Object.prototype.hasOwnProperty.call(obj, "deviceList")) backendStore.setDeviceList(obj.deviceList);
      if (Object.prototype.hasOwnProperty.call(obj, "voiceList")) backendStore.setVoiceList(obj.voiceList);
      if (Object.prototype.hasOwnProperty.call(obj, "liveState")) {
        backendStore.setLiveState(obj.liveState);
      }
      if (Object.prototype.hasOwnProperty.call(obj, "is_connect")) backendStore.setIsConnect(obj.is_connect);
      if (Object.prototype.hasOwnProperty.call(obj, "isConnect")) backendStore.setIsConnect(obj.isConnect);
      if (Object.prototype.hasOwnProperty.call(obj, "audio_status")) {
        backendStore.setAudioStatus(obj.audio_status);
        setAudioPlayingStable(backendStore.audioPlaying);
      }
      if (Object.prototype.hasOwnProperty.call(obj, "audioStatus")) {
        backendStore.setAudioStatus(obj.audioStatus);
        setAudioPlayingStable(backendStore.audioPlaying);
      }
      if (Object.prototype.hasOwnProperty.call(obj, "audio_level")) {
        backendStore.setAudioLevel(obj.audio_level);
      }
      if (Object.prototype.hasOwnProperty.call(obj, "audioLevel")) {
        backendStore.setAudioLevel(obj.audioLevel);
      }

      let hasAgentStatus = false;
      const incomingAgentStatus = obj.agent_status ?? obj.agentStatus;
      if (incomingAgentStatus) {
        const sid = systemStore.currentSystemId;
        const next = String(incomingAgentStatus || "").toLowerCase();
        const hasPanelMsgText = typeof obj.panelMsg === "string" && String(obj.panelMsg).trim().length > 0;
        const isBareListening = next === "listening" && !hasPanelMsgText;
        if (!isBareListening && ["idle", "wake_pending", "listening", "thinking", "speaking"].includes(next)) {
          systemStore.setAgentStatus(sid, next);
          hasAgentStatus = true;
        }
      }

      const systemSwitch = obj.systemSwitch;
      if (systemSwitch && typeof systemSwitch === "object") {
        const mode = String(systemSwitch.mode || "").toLowerCase();
        if (mode === "sisi" || mode === "liuye") {
          systemStore.setCurrentSystem(mode);
          systemStore.setActiveAudioSystem(mode);
          triggerUiShake();
          push("status", "info", "systemSwitch", `mode=${mode}`, systemSwitch);
        }
      }

      const audioEvent = obj.audio_event || obj.audioEvent;
      if (audioEvent === "start") {
        setAudioPlayingStable(true);
      }
      if (audioEvent === "complete" || audioEvent === "finished") {
        setAudioPlayingStable(false);
      }

      if (obj.type === "play_start") {
        setAudioPlayingStable(true);
      }
      if (obj.type === "play_finished") {
        setAudioPlayingStable(false);
      }

      const audioCmd = obj.audio_command || obj.audioCommand;
      if (audioCmd === "start") {
        setAudioPlayingStable(true);
      }
      if (audioCmd === "stop") {
        setAudioPlayingStable(false);
      }

      const musicEvent = obj.music_event || obj.musicEvent;
      if (musicEvent) {
        const ev = String(musicEvent);
        const info = obj.music_info || obj.musicInfo || {
          file: obj.music_file || obj.musicFile || "",
          title: obj.music_title || obj.musicTitle || ""
        };
        const playing = ev === "start" || ev === "playing" || ev === "resume";
        backendStore.setMusicState(playing, info);
        push("audio", "info", "music_event", `${ev}${info?.title ? `: ${info.title}` : ""}`, obj);
      }

      const controlIntent = obj.control_intent || obj.controlIntent;
      if (controlIntent && typeof controlIntent === "object") {
        const action = String(controlIntent.action || controlIntent.intent || "").trim();
        const payload = {
          ...controlIntent,
          action: action || String(controlIntent.intent || "").trim(),
          _received_at: Date.now()
        };
        push("status", "info", "control_intent", action || "intent", payload);
        emitControlIntentEvent(payload);
      }

      if (obj.panelMsg) {
        // Step 1: disable frontend text inference from panelMsg.
        // Legacy keyword matching branch is intentionally disabled.
        push("status", "info", "panelMsg", String(obj.panelMsg), obj);
      }

      if (obj.panelReply) {
        const panelReply = obj.panelReply;
        const sid = resolveReplySystemId(panelReply, systemStore.currentSystemId);
        const role = resolveReplyRole(panelReply);
        const rawContent = normalizeReplyContent(panelReply?.content);
        const phase = String(panelReply?.phase || "");
        const phaseLower = phase.toLowerCase();
        const phaseFinal =
          phaseLower === "final" ||
          phaseLower.includes("final") ||
          phase.includes("\u6700\u7ec8");
        const isIntermediate = !!panelReply?.is_intermediate || (role === "assistant" && !!phase && !phaseFinal);
        const isFinal = !isIntermediate;
        const normalized = normalizeStreamingChunk(rawContent);
        const attachments = normalizeReplyAttachments(panelReply?.attachments);
        const hasAttachments = attachments.length > 0;

        const meta = {
          username: panelReply?.username || (role === "user" ? "User" : "SmartSisi"),
          source: "ws.panelReply",
          raw_type: panelReply?.type,
          uid: panelReply?.uid,
          backend_msg_id: panelReply?.id,
          phase,
          is_intermediate: !!panelReply?.is_intermediate
        };
        if (panelReply?.audio_status || panelReply?.audioStatus) {
          backendStore.setAudioStatus(panelReply?.audio_status || panelReply?.audioStatus);
          setAudioPlayingStable(backendStore.audioPlaying);
        }

        if (role === "assistant") {
          // Don't slam status to idle here 闂?let FlowChips derive it from
          // stream_open / audioPlaying / musicPlaying signals instead.
          // Only transition thinking闂傚倷鐒﹂崜姘跺磻閸涱喗鍙忛柡鍕妇e when the final chunk closes the stream
          // AND audio is not playing.
          // Step 1: disable frontend idle override on panelReply final chunks.
          // if (isFinal && !backendStore.audioPlaying) systemStore.setAgentStatus(sid, "idle");
          if (systemStore.streamAbortBySystem?.[sid]) return;

          const openId = systemStore.openStreamMessageIdBySystem?.[sid];
          if (openId) {
            const openMsg = findMessageById(systemStore, sid, openId);
            if (openMsg) {
              const next = mergeAssistantText(openMsg.content, normalized);
              systemStore.updateMessage({
                system_id: sid,
                id: openId,
                patch: {
                  content: next,
                  attachments: hasAttachments ? attachments : (openMsg.attachments || []),
                  meta: { ...(openMsg.meta || {}), ...meta, pending_reply: false, stream_open: !isFinal }
                }
              });
              if (isFinal) systemStore.clearOpenStreamMessage(sid, openId);
              return;
            }
            systemStore.clearOpenStreamMessage(sid, openId);
          }

          const existing = findAssistantByBackendId(systemStore, sid, meta.backend_msg_id);
          if (existing) {
            const next = mergeAssistantText(existing.content, normalized);
            systemStore.updateMessage({
              system_id: sid,
              id: existing.id,
              patch: {
                content: next,
                attachments: hasAttachments ? attachments : (existing.attachments || []),
                meta: { ...existing.meta, ...meta, stream_open: !isFinal }
              }
            });
            if (!isFinal) systemStore.setOpenStreamMessage(sid, existing.id);
            if (isFinal) systemStore.clearOpenStreamMessage(sid, existing.id);
          } else {
            const patched = patchAssistantPlaceholder(systemStore, sid, normalized, meta, !isFinal, attachments);
            const tail = !patched ? findAssistantStreamTail(systemStore, sid) : null;
            const recent = !patched ? findAssistantAfterLastUser(systemStore, sid) : null;
            const target = tail || recent;
            if (target) {
              const next = mergeAssistantText(target.content, normalized);
              systemStore.updateMessage({
                system_id: sid,
                id: target.id,
                patch: {
                  content: next,
                  attachments: hasAttachments ? attachments : (target.attachments || []),
                  meta: { ...(target.meta || {}), ...meta, stream_open: !isFinal }
                }
              });
              if (!isFinal) systemStore.setOpenStreamMessage(sid, target.id);
              if (isFinal) systemStore.clearOpenStreamMessage(sid, target.id);
            } else if (normalized || hasAttachments) {
              const newId = systemStore.addMessage({
                system_id: sid,
                role,
                content: normalized || "",
                attachments,
                meta: { ...meta, stream_open: !isFinal }
              });
              if (!isFinal) systemStore.setOpenStreamMessage(sid, newId);
            }
          }
        } else if (rawContent) {
          const lastUser = findLastUserMessage(systemStore, sid);
          const lastUserTs = parseCreatedAt(lastUser);
          const lastUserIsLocal = lastUser?.meta?.source === "ui";
          const normalizedLast = normalizeForCompare(lastUser?.content || "");
          const normalizedRaw = normalizeForCompare(rawContent);
          const lastHasAttachments = !!(Array.isArray(lastUser?.attachments) && lastUser.attachments.length > 0);
          const looksMultimodalEcho =
            normalizedRaw.startsWith("多模态:") ||
            normalizedRaw.startsWith("multimodal:");
          const extendsLocalText = !!(normalizedLast && normalizedRaw.startsWith(normalizedLast));

          // If a local user message was just sent, treat member echo as metadata only.
          if (
            lastUser &&
            lastUserIsLocal &&
            (
              isRecent(lastUserTs, 12000) ||
              extendsLocalText ||
              (lastHasAttachments && looksMultimodalEcho)
            )
          ) {
            systemStore.updateMessage({
              system_id: sid,
              id: lastUser.id,
              patch: { meta: { ...(lastUser.meta || {}), ...meta } }
            });
            return;
          }
          const dup = lastUser && normalizedLast === normalizedRaw;
          if (dup) {
            systemStore.updateMessage({
              system_id: sid,
              id: lastUser.id,
              patch: { meta: { ...(lastUser.meta || {}), ...meta } }
            });
          } else if (!isDuplicateUserTail(systemStore, sid, rawContent)) {
            systemStore.addMessage({ system_id: sid, role, content: rawContent, attachments, meta });
          }
        }

        push("status", "info", "panelReply", `${panelReply?.type || "reply"}: ${rawContent}`, obj);
      }
    };
  }

  function refresh() {
    if (configStore.backend.mode !== "real") return disconnect();
    connect(configStore.backend.ws_url);
  }

  refresh();

  configStore.$subscribe(() => {
    refresh();
  });

  return { disconnect };
}
