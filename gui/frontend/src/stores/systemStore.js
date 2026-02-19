import { defineStore } from "pinia";

const SYSTEMS = [
  { id: "sisi", name: "思思" },
  { id: "liuye", name: "柳叶" }
];

const HISTORY_KEY = "smartsisi_history_v1";
const CURRENT_SYSTEM_KEY = "smartsisi_last_system_id_v1";
const HISTORY_LIMIT = 200;
const VALID_SYSTEM_IDS = new Set(SYSTEMS.map((s) => s.id));

function nowIso() {
  return new Date().toISOString();
}

function makeId() {
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

function normalizeSystemId(value, fallback = "sisi") {
  const sid = String(value || "").trim();
  if (VALID_SYSTEM_IDS.has(sid)) return sid;
  return fallback;
}

function normalizeAttachments(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const raw of list) {
    if (!raw || typeof raw !== "object") continue;
    const id = String(raw.id || "").trim();
    const kind = String(raw.kind || "").trim();
    const name = String(raw.name || "").trim();
    const mime = String(raw.mime || "").trim();
    const preview_url = String(raw.preview_url || "").trim();
    const download_url = String(raw.download_url || preview_url || "").trim();
    if (!id && !preview_url) continue;
    out.push({
      id: id || makeId(),
      kind: kind || "file",
      name: name || "attachment",
      mime: mime || "application/octet-stream",
      size: Number(raw.size || 0) || 0,
      preview_url,
      download_url,
      thumbnail_url: String(raw.thumbnail_url || "").trim(),
      duration_ms: Number(raw.duration_ms || 0) || 0,
      source: String(raw.source || "").trim() || "upload"
    });
  }
  return out;
}

function normalizeHistoryList(list) {
  if (!Array.isArray(list)) return [];
  const out = [];
  for (const item of list) {
    if (!item || typeof item !== "object") continue;
    const role = item.role === "user" || item.role === "assistant" ? item.role : null;
    if (!role) continue;
    const meta = item.meta && typeof item.meta === "object" ? { ...item.meta } : {};
    // pending_reply / stream_open are transient runtime flags and must not survive app restarts.
    if (role === "assistant") {
      meta.pending_reply = false;
      meta.stream_open = false;
    }
    out.push({
      id: item.id || makeId(),
      system_id: item.system_id || "sisi",
      role,
      content: typeof item.content === "string" ? item.content : String(item.content ?? ""),
      created_at: item.created_at || nowIso(),
      meta,
      attachments: normalizeAttachments(item.attachments)
    });
  }
  return out.slice(-HISTORY_LIMIT);
}

function resolveBackendRole(item) {
  const role = String(item?.role || "").trim().toLowerCase();
  if (role === "user" || role === "assistant") return role;
  const legacyType = String(item?.type || "").trim().toLowerCase();
  if (legacyType === "member" || legacyType === "user") return "user";
  return "assistant";
}

function resolveBackendSystemId(item) {
  const sid = normalizeSystemId(item?.system_id || item?.mode || "", "");
  if (sid) return sid;
  const legacyType = String(item?.type || "").trim().toLowerCase();
  if (legacyType === "liuye") return "liuye";
  return "sisi";
}

function normalizeBackendHistoryEntry(item) {
  if (!item || typeof item !== "object") return null;
  const role = resolveBackendRole(item);
  const system_id = resolveBackendSystemId(item);
  const contentRaw = item?.content ?? item?.text ?? "";
  const content = typeof contentRaw === "string" ? contentRaw : String(contentRaw);
  if (!content.trim()) return null;
  const created_at = String(item?.created_at || "").trim()
    || (Number.isFinite(Number(item?.createtime)) ? new Date(Number(item.createtime) * 1000).toISOString() : nowIso());
  const meta = item?.meta && typeof item.meta === "object" ? { ...item.meta } : {};
  return {
    id: item?.id || makeId(),
    system_id,
    role,
    content,
    created_at,
    meta,
    attachments: normalizeAttachments(item?.attachments)
  };
}

function mergeHistoryWithDedupe(currentList, incomingList) {
  const current = normalizeHistoryList(currentList);
  const incoming = normalizeHistoryList(incomingList);
  if (!incoming.length) return current;
  const seen = new Set(current.map((m) => `${m.role}|${m.created_at}|${m.content}`));
  const merged = current.slice();
  for (const msg of incoming) {
    const key = `${msg.role}|${msg.created_at}|${msg.content}`;
    if (seen.has(key)) continue;
    seen.add(key);
    merged.push(msg);
  }
  return normalizeHistoryList(merged);
}

function extractBackendHistoryBySystem(payload) {
  const systems = { sisi: [], liuye: [] };
  if (!payload || typeof payload !== "object") return systems;

  const appendItem = (raw) => {
    const normalized = normalizeBackendHistoryEntry(raw);
    if (!normalized) return;
    const sid = normalized.system_id === "liuye" ? "liuye" : "sisi";
    systems[sid].push(normalized);
  };

  const bySystems = payload?.systems;
  if (bySystems && typeof bySystems === "object") {
    for (const sid of ["sisi", "liuye"]) {
      const list = Array.isArray(bySystems?.[sid]) ? bySystems[sid] : [];
      for (const item of list) appendItem(item);
    }
    return systems;
  }

  const messages = Array.isArray(payload?.messages) ? payload.messages : [];
  if (messages.length) {
    for (const item of messages) appendItem(item);
    return systems;
  }

  const legacyList = Array.isArray(payload?.list) ? payload.list : [];
  for (const item of legacyList) appendItem(item);
  return systems;
}

function historyListSignature(list) {
  return normalizeHistoryList(list)
    .map((m) => `${m.role}|${m.created_at}|${m.content}`)
    .join("\n");
}

function loadPersistedMessages() {
  if (typeof window === "undefined") return { sisi: [], liuye: [] };
  try {
    const raw = localStorage.getItem(HISTORY_KEY);
    if (!raw) return { sisi: [], liuye: [] };
    const data = JSON.parse(raw);
    return {
      sisi: normalizeHistoryList(data?.sisi),
      liuye: normalizeHistoryList(data?.liuye)
    };
  } catch {
    return { sisi: [], liuye: [] };
  }
}

function loadPersistedCurrentSystem() {
  if (typeof window === "undefined") return "sisi";
  try {
    return normalizeSystemId(localStorage.getItem(CURRENT_SYSTEM_KEY), "sisi");
  } catch {
    return "sisi";
  }
}

function persistMessages(messagesBySystem) {
  if (typeof window === "undefined") return;
  try {
    const payload = {
      sisi: normalizeHistoryList(messagesBySystem?.sisi),
      liuye: normalizeHistoryList(messagesBySystem?.liuye)
    };
    localStorage.setItem(HISTORY_KEY, JSON.stringify(payload));
  } catch {}
}

function persistCurrentSystem(systemId) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(CURRENT_SYSTEM_KEY, normalizeSystemId(systemId, "sisi"));
  } catch {}
}

export const useSystemStore = defineStore("system", {
  state: () => ({
    systems: SYSTEMS,
    currentSystemId: loadPersistedCurrentSystem(),
    activeAudioSystemId: "sisi",
    agentStatusBySystem: {
      sisi: "idle",
      liuye: "idle"
    },
    streamAbortBySystem: {
      sisi: false,
      liuye: false
    },
    openStreamMessageIdBySystem: {
      sisi: null,
      liuye: null
    },
    tracesById: {},
    messagesBySystem: loadPersistedMessages(),
    _storageSyncReady: false,
    _storageSyncHandler: null
  }),
  getters: {
    currentSystem(state) {
      return state.systems.find((s) => s.id === state.currentSystemId) || state.systems[0];
    },
    currentMessages(state) {
      return state.messagesBySystem[state.currentSystemId] || [];
    }
  },
  actions: {
    initStorageSync() {
      if (this._storageSyncReady || typeof window === "undefined") return;
      const onStorage = (ev) => {
        const key = String(ev?.key || "");
        if (key === HISTORY_KEY) {
          this.messagesBySystem = loadPersistedMessages();
          return;
        }
        if (key === CURRENT_SYSTEM_KEY) {
          const sid = loadPersistedCurrentSystem();
          if (sid !== this.currentSystemId) this.currentSystemId = sid;
        }
      };
      window.addEventListener("storage", onStorage);
      this._storageSyncHandler = onStorage;
      this._storageSyncReady = true;
    },
    disposeStorageSync() {
      if (!this._storageSyncReady || typeof window === "undefined") return;
      if (typeof this._storageSyncHandler === "function") {
        try {
          window.removeEventListener("storage", this._storageSyncHandler);
        } catch {}
      }
      this._storageSyncHandler = null;
      this._storageSyncReady = false;
    },
    setCurrentSystem(systemId) {
      const sid = normalizeSystemId(systemId, "");
      if (!sid) return;
      this.currentSystemId = sid;
      persistCurrentSystem(sid);
    },
    hydrateHistoryFromBackend(payload = {}) {
      const incoming = extractBackendHistoryBySystem(payload);
      const mergedSisi = mergeHistoryWithDedupe(this.messagesBySystem?.sisi || [], incoming.sisi || []);
      const mergedLiuye = mergeHistoryWithDedupe(this.messagesBySystem?.liuye || [], incoming.liuye || []);

      const oldSisi = this.messagesBySystem?.sisi || [];
      const oldLiuye = this.messagesBySystem?.liuye || [];
      const changed = historyListSignature(mergedSisi) !== historyListSignature(oldSisi)
        || historyListSignature(mergedLiuye) !== historyListSignature(oldLiuye);
      if (!changed) return false;

      this.messagesBySystem = {
        ...this.messagesBySystem,
        sisi: mergedSisi,
        liuye: mergedLiuye
      };
      persistMessages(this.messagesBySystem);
      return true;
    },
    setActiveAudioSystem(systemId) {
      if (!this.systems.some((s) => s.id === systemId)) return;
      this.activeAudioSystemId = systemId;
    },
    setAgentStatus(systemId, status) {
      if (!this.agentStatusBySystem[systemId]) this.agentStatusBySystem[systemId] = "idle";
      this.agentStatusBySystem[systemId] = status;
    },
    addMessage({ system_id, role, content, meta = {}, attachments = [] }) {
      if (!this.messagesBySystem[system_id]) this.messagesBySystem[system_id] = [];
      if (role === "user") {
        this.streamAbortBySystem[system_id] = false;
      }
      const message = {
        id: makeId(),
        system_id,
        role,
        content,
        created_at: nowIso(),
        meta,
        attachments: normalizeAttachments(attachments)
      };
      this.messagesBySystem[system_id].push(message);
      persistMessages(this.messagesBySystem);
      return message.id;
    },
    setStreamAbort(systemId, value) {
      if (!this.streamAbortBySystem[systemId]) this.streamAbortBySystem[systemId] = false;
      this.streamAbortBySystem[systemId] = !!value;
    },
    setOpenStreamMessage(systemId, messageId) {
      if (!this.openStreamMessageIdBySystem[systemId]) this.openStreamMessageIdBySystem[systemId] = null;
      this.openStreamMessageIdBySystem[systemId] = messageId || null;
    },
    clearOpenStreamMessage(systemId, messageId = null) {
      if (!this.openStreamMessageIdBySystem[systemId]) this.openStreamMessageIdBySystem[systemId] = null;
      if (messageId && this.openStreamMessageIdBySystem[systemId] !== messageId) return false;
      this.openStreamMessageIdBySystem[systemId] = null;
      return true;
    },
    closeOpenStream(systemId) {
      const list = this.messagesBySystem[systemId] || [];
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const m = list[i];
        if (m?.role !== "assistant") continue;
        if (m?.meta?.stream_open || m?.meta?.pending_reply) {
          list[i] = {
            ...m,
            meta: { ...(m.meta || {}), stream_open: false, pending_reply: false }
          };
          this.clearOpenStreamMessage(systemId, m.id);
          persistMessages(this.messagesBySystem);
          return true;
        }
        break;
      }
      return false;
    },
    clearStreamingFlags(systemId = null) {
      const targetSystemIds = systemId
        ? [systemId]
        : (Array.isArray(this.systems) ? this.systems.map((s) => s.id) : ["sisi", "liuye"]);
      let changed = false;
      for (const sid of targetSystemIds) {
        const list = this.messagesBySystem[sid] || [];
        for (let i = 0; i < list.length; i += 1) {
          const m = list[i];
          if (m?.role !== "assistant") continue;
          if (!m?.meta?.pending_reply && !m?.meta?.stream_open) continue;
          list[i] = {
            ...m,
            meta: { ...(m.meta || {}), pending_reply: false, stream_open: false }
          };
          changed = true;
        }
        this.openStreamMessageIdBySystem[sid] = null;
      }
      if (changed) persistMessages(this.messagesBySystem);
      return changed;
    },
    updateMessage({ system_id, id, patch }) {
      const list = this.messagesBySystem[system_id] || [];
      const idx = list.findIndex((m) => m.id === id);
      if (idx === -1) return false;
      const nextAttachments = Object.prototype.hasOwnProperty.call(patch || {}, "attachments")
        ? normalizeAttachments(patch.attachments)
        : list[idx].attachments || [];
      list[idx] = {
        ...list[idx],
        ...patch,
        attachments: nextAttachments,
        meta: { ...(list[idx].meta || {}), ...(patch.meta || {}) }
      };
      persistMessages(this.messagesBySystem);
      return true;
    },
    createTrace({ system_id, messageId, stages }) {
      const traceId = makeId();
      this.tracesById[traceId] = {
        id: traceId,
        system_id,
        message_id: messageId,
        created_at: Date.now(),
        stages: stages.map((s) => ({
          key: s.key,
          label: s.label,
          state: s.state || "pending",
          outcome: s.outcome || "done",
          started_at: null,
          ended_at: null
        }))
      };
      return traceId;
    },
    setTraceStageState({ traceId, stageKey, state }) {
      const trace = this.tracesById[traceId];
      if (!trace) return false;
      const stage = trace.stages.find((s) => s.key === stageKey);
      if (!stage) return false;

      const now = Date.now();
      if (state === "running" && stage.started_at == null) stage.started_at = now;
      if ((state === "done" || state === "error") && stage.ended_at == null) stage.ended_at = now;
      stage.state = state;
      trace.updated_at = now;
      return true;
    }
  }
});
