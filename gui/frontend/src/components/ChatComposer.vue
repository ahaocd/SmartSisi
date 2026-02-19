<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { NDropdown, NInput, NModal, useNotification } from "naive-ui";
import { useSystemStore } from "../stores/systemStore";
import { useConfigStore } from "../stores/configStore";
import { useBackendStore } from "../stores/backendStore";
import {
  apiGetAllConfig,
  apiGetModels,
  apiGetRunStatus,
  apiSaveAllConfig,
  apiStartLive,
  apiSubmit,
  apiToStopTalking,
  apiV1RealtimeEvent,
  apiV1RealtimeSession,
  apiV1SendMultimodalMessage,
  apiV1UploadFile
} from "../api/sisiApi";
import { buildBackendPatchFromUiConfig } from "../api/configBridge";
import { getIcon } from "../ui/icons";

const systemStore = useSystemStore();
const configStore = useConfigStore();
const backendStore = useBackendStore();
const notify = useNotification();

const text = ref("");
const sending = ref(false);
const voiceBusy = ref(false);
const duplexBusy = ref(false);
const showModelModal = ref(false);
const mode = ref("think");
const customModelDraft = ref("");
const fileInput = ref(null);
const attachments = ref([]);

const MAX_IMAGE_MB = 20;
const MAX_VIDEO_MB = 500;
const CONTROL_ACTION_WHITELIST = new Set([
  "interrupt_output",
  "open_multimodal",
  "capture_frames_and_analyze",
  "video_call_start",
  "video_call_stop"
]);

const realtimeSession = ref({
  active: false,
  provider: "",
  session_id: "",
  model: ""
});
const controlIntentBusy = ref(false);

const recentModels = ref(loadRecentModels());
const backendModels = ref([]);

function loadRecentModels() {
  try {
    const raw = localStorage.getItem("smartsisi_recent_models_v1");
    const arr = raw ? JSON.parse(raw) : [];
    return Array.isArray(arr) ? arr.filter((s) => typeof s === "string" && s.trim()) : [];
  } catch {
    return [];
  }
}

function saveRecentModels(list) {
  try {
    localStorage.setItem("smartsisi_recent_models_v1", JSON.stringify(list));
  } catch {}
}

const currentModel = computed(() => {
  const v = configStore.systemConfig(systemStore.currentSystemId).llm_model;
  return String(v || "default").trim() || "default";
});

function setModel(modelName) {
  const v = String(modelName || "").trim();
  if (!v) return;
  configStore.patchSystem(systemStore.currentSystemId, { llm_model: v });
  if (v !== "default") {
    const next = [v, ...recentModels.value.filter((m) => m !== v)].slice(0, 6);
    recentModels.value = next;
    saveRecentModels(next);
  }
}

const modelOptions = computed(() => {
  const base = [{ label: "默认", key: "default" }];
  const remote = backendModels.value
    .map((m) => ({
      label: String(m?.name || m?.id || m?.label || m?.key || "").trim() || "未命名模型",
      key: String(m?.id || m?.key || m?.label || "").trim()
    }))
    .filter((m) => m.key);
  const recent = recentModels.value.map((m) => ({ label: m, key: m }));
  const merged = [...base, ...remote, ...recent];
  const seen = new Set();
  return merged.filter((m) => {
    if (seen.has(m.key)) return false;
    seen.add(m.key);
    return true;
  });
});

const modeLabel = computed(() => (mode.value === "fast" ? "快速" : "思考"));
const modeOptions = computed(() => [
  { label: "思考", key: "think" },
  { label: "快速", key: "fast" },
  { label: "选择", key: "__model" }
]);
const duplexOptions = computed(() => [
  { label: "稳聊模式（半双工）", key: "half" },
  { label: "畅聊模式（全双工）", key: "full" }
]);
const duplexMode = computed(() => (String(configStore.shared.duplex_mode || "").trim().toLowerCase() === "full" ? "full" : "half"));
const duplexLabel = computed(() => (duplexMode.value === "full" ? "畅聊" : "稳聊"));
const duplexHint = computed(() =>
  duplexMode.value === "full"
    ? "畅聊模式（全双工）：可以边听边说，建议搭配耳机或AEC。"
    : "稳聊模式（半双工）：说话期间抑制回放，更稳更抗串音。"
);

function iconHtml(name) {
  return getIcon("composer", name);
}

function onModeSelect(key) {
  if (key === "__model") {
    customModelDraft.value = currentModel.value;
    showModelModal.value = true;
    return;
  }
  if (key === "fast" || key === "think") {
    mode.value = key;
    setModel(key === "fast" ? "4.1fast" : "4.1THINK");
  }
}

async function loadBackendModels() {
  const httpBase = configStore.backend.http_base;
  try {
    const res = await apiGetModels(httpBase);
    backendModels.value = Array.isArray(res?.data) ? res.data : [];
  } catch (e) {
    notify.warning({
      title: "模型列表不可用",
      content: String(e?.message || e),
      duration: 2000
    });
  }
}

onMounted(() => {
  loadBackendModels();
  if (typeof window !== "undefined") {
    window.addEventListener("smartsisi:control-intent", onControlIntentEvent);
  }
});

onBeforeUnmount(() => {
  if (typeof window !== "undefined") {
    window.removeEventListener("smartsisi:control-intent", onControlIntentEvent);
  }
});

function waitMs(ms) {
  return new Promise((resolve) => setTimeout(resolve, Math.max(0, Number(ms) || 0)));
}

function clampInt(value, fallback, min, max) {
  const n = Number(value);
  if (!Number.isFinite(n)) return fallback;
  const i = Math.round(n);
  return Math.min(max, Math.max(min, i));
}

function resolveControlAction(payload) {
  const raw = String(payload?.action || payload?.intent || "").trim().toLowerCase();
  if (raw === "image_analysis_capture") return "capture_frames_and_analyze";
  return raw;
}

function resolveControlProvider(payload) {
  const args = payload?.args && typeof payload.args === "object" ? payload.args : {};
  const fromArgs = String(args.provider || "").trim().toLowerCase();
  const fromPayload = String(payload?.provider || "").trim().toLowerCase();
  if (fromArgs) return fromArgs;
  if (fromPayload) return fromPayload;
  return "openai";
}

async function captureFramesFromCamera(args = {}) {
  if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia) {
    throw new Error("当前环境不支持摄像头采集。");
  }

  const frameCount = clampInt(args.frames, 3, 1, 6);
  const intervalMs = clampInt(args.interval_ms, 220, 120, 1500);
  const idealWidth = clampInt(args.width, 1280, 640, 1920);
  const idealHeight = clampInt(args.height, 720, 360, 1080);

  const stream = await navigator.mediaDevices.getUserMedia({
    video: {
      width: { ideal: idealWidth },
      height: { ideal: idealHeight }
    },
    audio: false
  });

  let videoEl = null;
  try {
    videoEl = document.createElement("video");
    videoEl.autoplay = true;
    videoEl.muted = true;
    videoEl.playsInline = true;
    videoEl.srcObject = stream;
    await videoEl.play().catch(() => {});
    await waitMs(260);

    const track = stream.getVideoTracks?.()[0] || null;
    const settings = track?.getSettings?.() || {};
    const frameW = clampInt(settings.width, Number(videoEl.videoWidth || idealWidth), 640, 2560);
    const frameH = clampInt(settings.height, Number(videoEl.videoHeight || idealHeight), 360, 1440);

    const canvas = document.createElement("canvas");
    canvas.width = frameW;
    canvas.height = frameH;
    const ctx = canvas.getContext("2d", { alpha: false });
    if (!ctx) throw new Error("摄像头帧缓冲初始化失败。");

    const files = [];
    for (let i = 0; i < frameCount; i += 1) {
      ctx.drawImage(videoEl, 0, 0, frameW, frameH);
      // Keep a high JPEG quality for image-analysis prompts.
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/jpeg", 0.92));
      if (blob) {
        files.push(
          new File([blob], `capture_${Date.now()}_${i + 1}.jpg`, {
            type: "image/jpeg"
          })
        );
      }
      if (i < frameCount - 1) await waitMs(intervalMs);
    }
    if (!files.length) {
      throw new Error("未能捕获到可用画面。");
    }
    return files;
  } finally {
    try {
      for (const t of stream.getTracks?.() || []) t.stop();
    } catch {}
    try {
      if (videoEl) {
        videoEl.pause();
        videoEl.srcObject = null;
      }
    } catch {}
  }
}

async function startRealtimeByIntent(payload = {}) {
  await ensureBackendRunning();
  const provider = resolveControlProvider(payload);
  const args = payload?.args && typeof payload.args === "object" ? payload.args : {};
  const sessionOverrides = args.session && typeof args.session === "object" ? args.session : {};

  const data = await apiV1RealtimeSession(configStore.backend.http_base, {
    provider,
    persona: systemStore.currentSystemId,
    system_id: systemStore.currentSystemId,
    username: "User",
    ttl_seconds: clampInt(args.ttl_seconds, 300, 30, 3600),
    issue_client_secret: args.issue_client_secret,
    server_vad_enabled: args.server_vad_enabled,
    interrupt_response_enabled: args.interrupt_response_enabled,
    vad_threshold: args.vad_threshold,
    vad_prefix_padding_ms: args.vad_prefix_padding_ms,
    vad_silence_duration_ms: args.vad_silence_duration_ms,
    session: sessionOverrides
  });

  const nextProvider = String(data?.provider || provider || "").trim().toLowerCase() || "openai";
  const sessionId = String(
    data?.session_id ||
      data?.sessionId ||
      data?.client_secret?.session_id ||
      data?.client_secret?.raw?.session_id ||
      ""
  ).trim();

  realtimeSession.value = {
    active: true,
    provider: nextProvider,
    session_id: sessionId,
    model: String(data?.model || "").trim()
  };

  notify.success({
    title: "实时会话已就绪",
    content: `${nextProvider}${realtimeSession.value.model ? ` / ${realtimeSession.value.model}` : ""}`,
    duration: 1800
  });
}

async function stopRealtimeByIntent(payload = {}) {
  const provider = String(realtimeSession.value.provider || resolveControlProvider(payload) || "openai").trim().toLowerCase();
  const sessionId = String(realtimeSession.value.session_id || "").trim();
  try {
    await apiV1RealtimeEvent(configStore.backend.http_base, {
      provider,
      session_id: sessionId,
      username: "User",
      emit_tts_on_done: false,
      emit_tts_on_segment: false,
      event: {
        type: "response.cancel"
      }
    });
  } catch {}

  realtimeSession.value = {
    active: false,
    provider: "",
    session_id: "",
    model: ""
  };
  notify.info({ title: "实时会话已结束", duration: 1400 });
}

async function executeControlIntent(payload = {}) {
  const action = resolveControlAction(payload);
  if (!CONTROL_ACTION_WHITELIST.has(action)) return;

  if (action === "interrupt_output") {
    await stopStream();
    return;
  }

  if (action === "open_multimodal") {
    onPickFiles();
    return;
  }

  if (action === "capture_frames_and_analyze") {
    const args = payload?.args && typeof payload.args === "object" ? payload.args : {};
    const frames = await captureFramesFromCamera(args);
    await queueFiles(frames);
    if (!String(text.value || "").trim()) {
      text.value = String(args.prompt || "请分析这几帧画面并结合上下文回复。").trim();
    }
    await send();
    return;
  }

  if (action === "video_call_start") {
    await startRealtimeByIntent(payload);
    return;
  }

  if (action === "video_call_stop") {
    await stopRealtimeByIntent(payload);
  }
}

async function onControlIntentEvent(ev) {
  const payload = ev?.detail;
  if (!payload || typeof payload !== "object") return;
  const action = resolveControlAction(payload);
  if (!CONTROL_ACTION_WHITELIST.has(action)) return;
  if (controlIntentBusy.value) return;

  controlIntentBusy.value = true;
  try {
    await executeControlIntent(payload);
  } catch (e) {
    notify.warning({
      title: "命令执行失败",
      content: String(e?.message || e),
      duration: 2200
    });
  } finally {
    controlIntentBusy.value = false;
  }
}

async function ensureBackendRunning() {
  if (backendStore.liveState === 1) return true;
  const httpBase = configStore.backend.http_base;
  try {
    const st = await apiGetRunStatus(httpBase);
    if (st && typeof st === "object" && st.status === true) return true;
  } catch {}
  await apiStartLive(httpBase);
  return true;
}

function isObject(v) {
  return v != null && typeof v === "object" && !Array.isArray(v);
}

function cloneObj(v) {
  try {
    return JSON.parse(JSON.stringify(v ?? {}));
  } catch {
    return {};
  }
}

function normalizeDuplexMode(mode) {
  return String(mode || "").trim().toLowerCase() === "full" ? "full" : "half";
}

function withDuplexSystemConf(systemConf, mode) {
  const next = cloneObj(systemConf);
  if (!isObject(next.key)) next.key = {};
  next.key.half_duplex_enabled = mode === "half" ? "true" : "false";
  return next;
}

async function getConfigSnapshot(httpBase) {
  const snap = configStore.backendSnapshot;
  if (isObject(snap?.config_json) && isObject(snap?.system_conf)) {
    return {
      config_json: cloneObj(snap.config_json),
      system_conf: cloneObj(snap.system_conf)
    };
  }
  const fresh = await apiGetAllConfig(httpBase);
  configStore.setBackendSnapshot(fresh);
  return {
    config_json: cloneObj(fresh?.config_json),
    system_conf: cloneObj(fresh?.system_conf)
  };
}

let duplexPersistToken = 0;
let duplexChangeToken = 0;

async function persistDuplexMode(mode) {
  const token = ++duplexPersistToken;
  duplexBusy.value = true;
  const httpBase = configStore.backend.http_base;
  const snap = await getConfigSnapshot(httpBase);
  if (!isObject(snap.config_json) || !isObject(snap.system_conf)) {
    throw new Error("后端配置快照不完整，无法保存双工模式。");
  }
  const nextSystemConf = withDuplexSystemConf(snap.system_conf, mode);
  await apiSaveAllConfig(httpBase, {
    config_json: snap.config_json,
    system_conf: nextSystemConf
  });
  if (token !== duplexPersistToken) return;
  configStore.setBackendSnapshot({
    config_json: snap.config_json,
    system_conf: nextSystemConf
  });
}

async function setDuplexMode(nextModeRaw) {
  const nextMode = normalizeDuplexMode(nextModeRaw);
  const prevMode = normalizeDuplexMode(configStore.shared.duplex_mode);
  if (nextMode === prevMode && !duplexBusy.value) return;

  const changeToken = ++duplexChangeToken;
  configStore.patchShared({
    duplex_mode: nextMode,
    ptt_enabled: nextMode === "half"
  });

  try {
    await ensureBackendRunning();
    await persistDuplexMode(nextMode);
  } catch (e) {
    if (changeToken !== duplexChangeToken) return;
    configStore.patchShared({
      duplex_mode: prevMode,
      ptt_enabled: prevMode === "half"
    });
    notify.error({
      title: "双工模式保存失败",
      content: String(e?.message || e),
      duration: 2600
    });
  } finally {
    if (changeToken === duplexChangeToken) duplexBusy.value = false;
  }
}

function onDuplexSelect(key) {
  if (key !== "half" && key !== "full") return;
  setDuplexMode(key);
}

async function toggleVoiceMaster() {
  if (voiceBusy.value) return;
  const prev = !!configStore.shared.stt_enabled;
  const next = !prev;
  voiceBusy.value = true;
  configStore.patchShared({ stt_enabled: next, realtime_audio_enabled: next });

  const httpBase = configStore.backend.http_base;
  try {
    await ensureBackendRunning();
    const patch = buildBackendPatchFromUiConfig(configStore.config);
    await apiSubmit(httpBase, patch);
  } catch (e) {
    configStore.patchShared({ stt_enabled: prev, realtime_audio_enabled: prev });
    notify.error({
      title: next ? "语音开启失败" : "语音关闭失败",
      content: String(e?.message || e),
      duration: 2400
    });
  } finally {
    voiceBusy.value = false;
  }
}

function inferKind(file) {
  const mime = String(file?.type || "").toLowerCase();
  return mime.startsWith("video/") ? "video" : "image";
}

function isImageAttachment(att) {
  const kind = String(att?.kind || "").toLowerCase();
  const mime = String(att?.mime || "").toLowerCase();
  return kind === "image" || mime.startsWith("image/");
}

function isVideoAttachment(att) {
  const kind = String(att?.kind || "").toLowerCase();
  const mime = String(att?.mime || "").toLowerCase();
  return kind === "video" || mime.startsWith("video/");
}

function validateFile(file) {
  const kind = inferKind(file);
  const maxMB = kind === "video" ? MAX_VIDEO_MB : MAX_IMAGE_MB;
  const sizeMB = Number(file?.size || 0) / 1024 / 1024;

  if (!file?.type || (!file.type.startsWith("image/") && !file.type.startsWith("video/"))) {
    throw new Error("仅支持图片或视频文件");
  }
  if (sizeMB > maxMB) {
    throw new Error(`${kind === "video" ? "视频" : "图片"}超过 ${maxMB}MB 限制`);
  }
  return kind;
}

async function uploadOneFile(file) {
  const kind = validateFile(file);
  const httpBase = configStore.backend.http_base;
  const res = await apiV1UploadFile(httpBase, file);
  const att = res?.attachment || {};

  attachments.value.push({
    id: att.id,
    kind: att.kind || kind,
    name: att.name || file.name,
    mime: att.mime || file.type,
    size: att.size || file.size,
    preview_url: att.preview_url || "",
    download_url: att.download_url || att.preview_url || "",
    source: "upload"
  });
}

async function queueFiles(fileList) {
  const files = Array.from(fileList || []);
  if (!files.length) return;

  for (const file of files) {
    try {
      await uploadOneFile(file);
    } catch (e) {
      notify.error({
        title: "文件上传失败",
        content: String(e?.message || e),
        duration: 2600
      });
    }
  }
}

function onPickFiles() {
  fileInput.value?.click?.();
}

async function onFileInputChange(ev) {
  const files = ev?.target?.files;
  await queueFiles(files);
  if (ev?.target) ev.target.value = "";
}

async function onPaste(ev) {
  const items = Array.from(ev?.clipboardData?.items || []);
  const files = [];
  for (const item of items) {
    if (item.kind !== "file") continue;
    const f = item.getAsFile?.();
    if (!f) continue;
    if (f.type.startsWith("image/") || f.type.startsWith("video/")) files.push(f);
  }
  if (!files.length) return;
  ev.preventDefault();
  await queueFiles(files);
}

function onDragOver(ev) {
  ev.preventDefault();
}

async function onDrop(ev) {
  ev.preventDefault();
  const files = Array.from(ev?.dataTransfer?.files || []);
  if (!files.length) return;
  await queueFiles(files);
}

function removeAttachment(attId) {
  attachments.value = attachments.value.filter((x) => x.id !== attId);
}

function toStoreAttachment(att) {
  return {
    id: att.id,
    kind: att.kind,
    name: att.name,
    mime: att.mime,
    size: att.size,
    preview_url: att.preview_url,
    download_url: att.download_url,
    source: att.source || "upload"
  };
}

function buildDisplayText(msg, atts) {
  if (msg) return msg;
  const n = Array.isArray(atts) ? atts.length : 0;
  return n > 0 ? `已发送 ${n} 个附件` : "";
}

async function send() {
  const msg = text.value.trim();
  const atts = attachments.value.slice();
  if ((!msg && atts.length === 0) || sending.value) return;

  sending.value = true;
  try {
    const system_id = systemStore.currentSystemId;
    systemStore.setStreamAbort(system_id, false);
    systemStore.clearStreamingFlags(system_id);
    systemStore.clearOpenStreamMessage(system_id);

    await ensureBackendRunning();

    systemStore.addMessage({
      system_id,
      role: "user",
      content: buildDisplayText(msg, atts),
      attachments: atts.map(toStoreAttachment),
      meta: { username: "User", source: "ui" }
    });

    const assistantMessageId = systemStore.addMessage({
      system_id,
      role: "assistant",
      content: "",
      meta: { username: "SmartSisi", pending_reply: true, stream_open: true }
    });
    systemStore.setOpenStreamMessage(system_id, assistantMessageId);

    const traceId = systemStore.createTrace({
      system_id,
      messageId: assistantMessageId,
      stages: [{ key: "llm", label: "LLM" }]
    });
    systemStore.updateMessage({
      system_id,
      id: assistantMessageId,
      patch: { meta: { trace_id: traceId, pending_reply: true } }
    });
    systemStore.setTraceStageState({ traceId, stageKey: "llm", state: "running" });

    try {
      const patch = buildBackendPatchFromUiConfig(configStore.config);
      await apiSubmit(configStore.backend.http_base, patch);
    } catch {}

    const parts = [];
    if (msg) parts.push({ type: "text", text: msg });
    for (const att of atts) {
      parts.push({
        type: att.kind === "video" ? "video" : "image",
        file_id: att.id,
        mime: att.mime,
        name: att.name,
        size: att.size
      });
    }

    const mmRes = await apiV1SendMultimodalMessage(configStore.backend.http_base, {
      username: "User",
      persona: system_id,
      system_id,
      parts
    });

    const artifacts = Array.isArray(mmRes?.artifacts) ? mmRes.artifacts : [];
    if (artifacts.length) {
      systemStore.updateMessage({
        system_id,
        id: assistantMessageId,
        patch: { attachments: artifacts }
      });
    }

    text.value = "";
    attachments.value = [];
  } catch (e) {
    systemStore.closeOpenStream(systemStore.currentSystemId);
    notify.error({ title: "发送失败", content: String(e?.message || e), duration: 2400 });
  } finally {
    sending.value = false;
  }
}

function onKeydown(e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    send();
  }
}

function onCustomModelOk() {
  const v = String(customModelDraft.value || "").trim();
  if (v) setModel(v);
  showModelModal.value = false;
}

const isStreaming = computed(() => {
  const sid = systemStore.currentSystemId;
  if (backendStore.audioPlaying) return true;
  if (systemStore.openStreamMessageIdBySystem?.[sid]) return true;

  const list = systemStore.currentMessages || [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    const m = list[i];
    if (m?.role !== "assistant") continue;
    return !!(m?.meta?.pending_reply || m?.meta?.stream_open);
  }
  return false;
});

async function stopStream() {
  const system_id = systemStore.currentSystemId;
  systemStore.setStreamAbort(system_id, true);
  systemStore.closeOpenStream(system_id);
  systemStore.clearOpenStreamMessage(system_id);
  // Status is backend-authoritative. Do not force idle from frontend actions.
  try {
    await apiToStopTalking(configStore.backend.http_base, { text: "stop" });
  } catch (e) {
    notify.error({ title: "鍋滄澶辫触", content: String(e?.message || e), duration: 2400 });
  }
}
</script>

<template>
  <div class="composer">
    <div v-if="attachments.length" class="attach-list">
      <div v-for="att in attachments" :key="att.id" class="attach-chip" :title="att.name || ''">
        <img
          v-if="isImageAttachment(att)"
          class="attach-thumb"
          :src="att.preview_url"
          :alt="att.name || 'image'"
          loading="lazy"
        />
        <video
          v-else-if="isVideoAttachment(att)"
          class="attach-thumb"
          :src="att.preview_url"
          muted
          preload="metadata"
        ></video>
        <span v-else class="attach-fallback">{{ (att.name || "file").slice(0, 1).toUpperCase() }}</span>
        <span class="attach-name">{{ att.name }}</span>
        <button class="chip-remove" @click="removeAttachment(att.id)">x</button>
      </div>
    </div>

    <div class="pill" :data-sending="sending ? '1' : '0'" @dragover="onDragOver" @drop="onDrop">
      <button class="pill-btn" aria-label="上传附件" @click="onPickFiles">
        <span class="ico" aria-hidden="true" v-html="iconHtml('plus')"></span>
      </button>

      <textarea
        v-model="text"
        class="pill-input"
        rows="1"
        placeholder="输入内容…（Enter 发送）"
        @keydown="onKeydown"
        @paste="onPaste"
      ></textarea>

      <input ref="fileInput" class="hidden-file" type="file" multiple accept="image/*,video/*" @change="onFileInputChange" />

      <n-dropdown :options="modeOptions" trigger="click" placement="top-end" @select="onModeSelect">
        <button class="pill-btn pill-mode" aria-label="模式选择">
          <span class="preset-txt">{{ modeLabel }}</span>
        </button>
      </n-dropdown>

      <n-dropdown :options="duplexOptions" trigger="click" placement="top-end" @select="onDuplexSelect">
        <button
          class="pill-btn pill-duplex"
          :class="{ busy: duplexBusy }"
          :disabled="duplexBusy"
          :title="duplexHint"
          aria-label="双工模式"
        >
          <span class="preset-txt">{{ duplexLabel }}</span>
        </button>
      </n-dropdown>

      <button
        class="pill-btn pill-mic"
        :class="{ off: !configStore.shared.stt_enabled }"
        :disabled="voiceBusy"
        aria-label="语音"
        @click="toggleVoiceMaster"
      >
        <span class="ico mic-ico" aria-hidden="true" v-html="iconHtml('mic')"></span>
        <span v-if="!configStore.shared.stt_enabled" class="mic-strike"></span>
      </button>

      <button class="pill-btn pill-send" :disabled="sending && !isStreaming" :aria-label="isStreaming ? '停止' : '发送'" @click="isStreaming ? stopStream() : send()">
        <span class="ico" aria-hidden="true" v-html="iconHtml(isStreaming ? 'stop' : 'send')"></span>
      </button>
    </div>

    <n-modal v-model:show="showModelModal" preset="card" title="选择模型" style="width: min(520px, 92vw)">
      <div style="display: grid; gap: 12px">
        <div class="model-list">
          <button v-for="m in modelOptions" :key="m.key" class="model-item" @click="setModel(m.key)">
            {{ m.label }}
          </button>
        </div>
        <n-input v-model:value="customModelDraft" placeholder="输入模型名" />
        <div style="display: flex; justify-content: flex-end; gap: 10px">
          <button class="mini-btn" @click="showModelModal = false">取消</button>
          <button class="mini-btn mini-btn--primary" @click="onCustomModelOk">确定</button>
        </div>
      </div>
    </n-modal>
  </div>
</template>

<style scoped>
.composer {
  width: 100%;
  max-width: var(--chat-max-w);
  margin: 0;
  position: sticky;
  bottom: 0;
  z-index: 20;
}

.attach-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 8px;
}

.attach-chip {
  position: relative;
  width: 64px;
  height: 64px;
  overflow: hidden;
  border-radius: 10px;
  border: 1px solid var(--stroke);
  background: rgba(0, 0, 0, 0.22);
}

.attach-thumb {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.attach-fallback {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  color: var(--text-0);
}

.attach-name {
  display: none;
}

.chip-remove {
  position: absolute;
  top: 4px;
  right: 4px;
  width: 18px;
  height: 18px;
  padding: 0;
  border: none;
  border-radius: 999px;
  background: rgba(0, 0, 0, 0.55);
  color: #fff;
  cursor: pointer;
  font-size: 12px;
  line-height: 18px;
  text-align: center;
}

.pill {
  width: 100%;
  min-height: 46px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, var(--chat-window-border-alpha, 0.2));
  background: rgba(255, 255, 255, calc(var(--chat-window-alpha, 0.06) * 0.85));
  backdrop-filter: blur(calc(var(--chat-window-blur, 8) * 1px)) saturate(1.2);
  box-shadow: 0 10px 22px rgba(0, 0, 0, 0.18);
  position: relative;
  isolation: isolate;
  overflow: visible;
}

.pill::before {
  content: "";
  position: absolute;
  inset: -2px -2px -5px -2px;
  border-radius: inherit;
  z-index: -1;
  opacity: 0;
  transform: translateY(2px) scale(0.98);
  transform-origin: center bottom;
  pointer-events: none;
  background: radial-gradient(
    84% 120% at 50% 78%,
    rgba(127, 223, 255, 0.26) 0%,
    rgba(247, 168, 198, 0.16) 48%,
    rgba(247, 168, 198, 0) 100%
  );
}

:global(body.ui-flash) .pill::before {
  animation: composer-breath 340ms ease-out;
}

@keyframes composer-breath {
  0% {
    opacity: 0;
    transform: translateY(2px) scale(0.96);
  }
  45% {
    opacity: 0.42;
    transform: translateY(2px) scale(1.01);
  }
  100% {
    opacity: 0;
    transform: translateY(2px) scale(1.03);
  }
}

.pill-btn {
  flex: 0 0 auto;
  height: 34px;
  min-width: 34px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-0);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: transform 150ms ease, opacity 150ms ease, background 150ms ease;
}

.pill-btn:hover {
  background: rgba(247, 168, 198, 0.1);
}

.pill-btn:active {
  transform: scale(0.97);
  opacity: 0.85;
}

.pill-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.pill-input {
  flex: 1 1 auto;
  min-width: 0;
  height: 34px;
  padding: 8px 10px;
  border: 0;
  outline: none;
  background: transparent;
  color: var(--text-0);
  font-family: var(--font-ui);
  font-size: 13px;
  line-height: 18px;
  resize: none;
  overflow: hidden;
}

.pill-input::placeholder {
  color: var(--text-2);
}

.hidden-file {
  display: none;
}

.pill-mode {
  flex: 0 0 auto;
  padding: 0 12px;
  border: 1px solid var(--stroke);
  min-width: 64px;
  justify-content: center;
}

.pill-send {
  background: rgba(247, 168, 198, 0.18);
}

.pill-duplex {
  flex: 0 0 auto;
  padding: 0 12px;
  border: 1px solid var(--stroke);
  min-width: 64px;
  justify-content: center;
}

.pill-duplex.busy {
  opacity: 0.72;
}

.ico :deep(svg) {
  width: 18px;
  height: 18px;
  display: block;
  stroke: rgba(172, 180, 196, 0.86);
  stroke-width: 1.35;
  paint-order: stroke fill;
  vector-effect: non-scaling-stroke;
  filter: drop-shadow(0 0 0.8px rgba(172, 180, 196, 0.86));
}

.mini-btn {
  height: 34px;
  padding: 0 12px;
  border-radius: 10px;
  border: 1px solid var(--stroke);
  background: var(--glass);
  color: var(--text-0);
  cursor: pointer;
  transition: transform 150ms ease, opacity 150ms ease, background 150ms ease;
}

.mini-btn:hover {
  background: var(--bg-card-hover);
  border-color: var(--stroke-hover);
}

.mini-btn:active {
  transform: scale(0.98);
  opacity: 0.9;
}

.mini-btn--primary {
  border-color: rgba(247, 168, 198, 0.32);
  background: var(--accent-muted);
}

.preset-txt {
  font-size: 12px;
  white-space: nowrap;
}

.pill-mic {
  position: relative;
}

.pill-mic.off {
  opacity: 0.5;
}

.mic-strike {
  position: absolute;
  top: 50%;
  left: 50%;
  width: 24px;
  height: 2px;
  background: var(--bad);
  transform: translate(-50%, -50%) rotate(-45deg);
  border-radius: 1px;
  pointer-events: none;
}

@media (max-width: 760px) {
  .pill {
    gap: 4px;
    padding: 5px;
  }

  .pill-btn {
    min-width: 30px;
    height: 30px;
    padding: 0 8px;
  }

  .pill-input {
    height: 30px;
    padding: 6px 8px;
    font-size: 12px;
  }

  .pill-mode,
  .pill-duplex {
    min-width: 56px;
    padding: 0 8px;
  }

  .preset-txt {
    font-size: 11px;
  }
}

.model-list {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.model-item {
  height: 34px;
  border-radius: 10px;
  border: 1px solid var(--stroke);
  background: var(--glass);
  color: var(--text-0);
  cursor: pointer;
  font-size: 12px;
  transition: background 150ms ease, border-color 150ms ease, transform 120ms ease;
}

.model-item:hover {
  background: var(--bg-card-hover);
  border-color: var(--stroke-hover);
}

.model-item:active {
  transform: scale(0.98);
}
</style>



