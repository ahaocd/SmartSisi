<script setup>
import { computed, onBeforeUnmount, ref } from "vue";
import { useRouter } from "vue-router";
import SettingRow from "./SettingRow.vue";
import PixelSlider from "./PixelSlider.vue";
import Live2DControls from "./Live2DControls.vue";
import CharacterPanel from "./CharacterPanel.vue";

import { useUiStore } from "../stores/uiStore";
import { useSystemStore } from "../stores/systemStore";
import { useConfigStore } from "../stores/configStore";
import { useBackendStore } from "../stores/backendStore";
import { useEventStore, EVENT_KINDS } from "../stores/eventStore";
import { idbDel, idbSet } from "../ui/idb";
import {
  apiSaveAllConfig,
  apiSubmit,
  apiToStopTalking,
  apiToWake,
  apiGetData,
  apiSendText,
  apiGetMemberList,
  apiBrowserCheck,
  apiGetMsg,
  apiAdoptMsg,
  apiToGreet,
  apiTransparentPass,
  apiGetTtsVoices,
  apiSetTtsVoices
} from "../api/sisiApi";
import { buildBackendPatchFromUiConfig, mergeUiPatchIntoBackendConfig } from "../api/configBridge";

const uiStore = useUiStore();
const systemStore = useSystemStore();
const configStore = useConfigStore();
const backendStore = useBackendStore();
const eventStore = useEventStore();
const router = useRouter();

const sectionTitle = computed(() => {
  const map = {
    audio: "音频（共享）",
    system: "系统（各自）",
    tools: "工具 / MCP / Skills",
    logs: "日志",
    events: "事件",
    appearance: "外观",
    avatar: "角色"
  };
  return map[uiStore.leftSection] || "设置";
});

const sttEngineOptions = [
  { label: "Whisper", value: "whisper" },
  { label: "Sherpa", value: "sherpa" },
  { label: "Vosk", value: "vosk" },
  { label: "其他", value: "other" }
];
const ttsEngineOptions = [
  { label: "Edge", value: "edge" },
  { label: "Ali", value: "ali" },
  { label: "Eleven", value: "eleven" },
  { label: "其他", value: "other" }
];
const interruptModeOptions = [
  { label: "强插（barge_in）", value: "barge_in" },
  { label: "柔和（soft）", value: "soft" },
  { label: "关闭（off）", value: "off" }
];
const langOptions = [
  { label: "中文（zh-CN）", value: "zh-CN" },
  { label: "English（en-US）", value: "en-US" }
];
const sampleRateOptions = [
  { label: "16k", value: 16000 },
  { label: "48k", value: 48000 }
];

const kindOptions = computed(() => ["all", ...EVENT_KINDS]);
const systemFilterOptions = computed(() => ["current", "all", ...systemStore.systems.map((s) => s.id)]);

const visibleEvents = computed(() => {
  const sys = eventStore.filterSystemId;
  const kind = eventStore.filterKind;
  const current = systemStore.currentSystemId;
  return eventStore.events.filter((e) => {
    if (sys === "current" && e.system_id !== current) return false;
    if (sys !== "current" && sys !== "all" && e.system_id !== sys) return false;
    if (kind !== "all" && e.kind !== kind) return false;
    return true;
  });
});

const promptDraft = ref("");
const bgFileInput = ref(null);

const apiBusy = ref(false);
const apiLog = ref("");
const sendUsername = ref("User");
const sendText = ref("");
const getMsgPayload = ref("{\"system_id\":\"sisi\",\"username\":\"User\",\"limit\":20}");
const adoptMsgPayload = ref("{\"id\":\"\"}");
const greetPayload = ref("{\"username\":\"User\",\"observation\":\"\"}");
const transparentPayload = ref("{\"user\":\"User\",\"text\":\"\"}");
const ttsSisiVoice = ref("");
const ttsLiuyeVoice = ref("");
const APPEARANCE_CONTINUOUS_KEYS = new Set(["background_blur", "inkfx_intensity"]);
const DOPAMINE_PALETTE_COUNT = 8;
let appearanceEventTimer = null;
let pendingAppearanceLog = null;

function syncPromptDraftFromStore() {
  promptDraft.value = configStore.systemConfig(systemStore.currentSystemId).system_prompt || "";
}
syncPromptDraftFromStore();

function onClose() {
  uiStore.closeLeft();
}

function setSys(k, v) {
  configStore.patchSystem(systemStore.currentSystemId, { [k]: v });
  if (k === "system_prompt") syncPromptDraftFromStore();
}

function pushUiEvent(level, title, message, payload = {}) {
  eventStore.pushEvent({
    system_id: systemStore.currentSystemId,
    kind: "status",
    level,
    title,
    message,
    payload
  });
}

function pushToolEvent(level, title, message, payload = {}) {
  eventStore.pushEvent({
    system_id: systemStore.currentSystemId,
    kind: "tool",
    level,
    title,
    message,
    payload
  });
}

function formatLog(label, data) {
  const stamp = new Date().toLocaleTimeString();
  const body = typeof data === "string" ? data : JSON.stringify(data, null, 2);
  return `[${stamp}] ${label}\n${body}`;
}

function parseJson(text, fallback = {}) {
  if (!text || !String(text).trim()) return fallback;
  return JSON.parse(text);
}

async function runApi(label, fn) {
  apiBusy.value = true;
  try {
    const res = await fn();
    apiLog.value = formatLog(label, res);
    pushToolEvent("success", label, "ok", typeof res === "string" ? { text: res } : res || {});
    return res;
  } catch (e) {
    const msg = String(e?.message || e);
    apiLog.value = formatLog(`${label} (error)`, msg);
    pushToolEvent("error", label, msg);
    return null;
  } finally {
    apiBusy.value = false;
  }
}

async function callGetData() {
  await runApi("POST /api/get-data", () => apiGetData(configStore.backend.http_base));
}

async function callSend() {
  await runApi("POST /api/send", () =>
    apiSendText(configStore.backend.http_base, { username: sendUsername.value, msg: sendText.value })
  );
}

async function callGetMemberList() {
  await runApi("POST /api/get-member-list", () => apiGetMemberList(configStore.backend.http_base));
}

async function callBrowserCheck() {
  await runApi("GET /api/browser-check", () => apiBrowserCheck(configStore.backend.http_base));
}

async function callGetMsg() {
  await runApi("POST /api/get-msg", () =>
    apiGetMsg(configStore.backend.http_base, parseJson(getMsgPayload.value))
  );
}

async function callAdoptMsg() {
  await runApi("POST /api/adopt_msg", () =>
    apiAdoptMsg(configStore.backend.http_base, parseJson(adoptMsgPayload.value))
  );
}

async function callToGreet() {
  await runApi("POST /to_greet", () =>
    apiToGreet(configStore.backend.http_base, parseJson(greetPayload.value))
  );
}

async function callTransparentPass() {
  await runApi("POST /transparent_pass", () =>
    apiTransparentPass(configStore.backend.http_base, parseJson(transparentPayload.value))
  );
}

async function callGetTtsVoices() {
  const res = await runApi("GET /api/tts/voices", () => apiGetTtsVoices(configStore.backend.http_base));
  if (res && typeof res === "object") {
    ttsSisiVoice.value = res.sisi_voice_uri || ttsSisiVoice.value;
    ttsLiuyeVoice.value = res.liuye_voice_uri || ttsLiuyeVoice.value;
  }
}

async function callSetTtsVoices() {
  const payload = {};
  if (ttsSisiVoice.value) payload.sisi_voice_uri = ttsSisiVoice.value;
  if (ttsLiuyeVoice.value) payload.liuye_voice_uri = ttsLiuyeVoice.value;
  await runApi("POST /api/tts/voices", () => apiSetTtsVoices(configStore.backend.http_base, payload));
}

const AUTO_SUBMIT_SHARED_KEYS = new Set([
  "stt_engine",
  "stt_enabled",
  "stt_device",
  "stt_sample_rate",
  "wake_enabled",
  "wake_word",
  "autoplay_enabled",
  "tts_enabled",
  "interrupt_enabled",
  "tts_voice"
]);

let submitTimer = null;
let saveAllTimer = null;

function scheduleBackendSubmit(reasonKey = "") {
  if (submitTimer) clearTimeout(submitTimer);
  submitTimer = setTimeout(async () => {
    submitTimer = null;
    try {
      const patch = buildBackendPatchFromUiConfig(configStore.config);
      const r = await apiSubmit(configStore.backend.http_base, patch);
      pushUiEvent("success", "配置已同步到后端", reasonKey ? `字段: ${reasonKey}` : "已调用 /api/submit", { response: r, patch });
    } catch (e) {
      pushUiEvent("error", "配置同步失败", String(e?.message || e), { key: reasonKey });
    }
  }, 380);
}

function scheduleBackendSaveAll(reasonKey = "") {
  const snap = configStore.backendSnapshot;
  if (!snap || !snap.config_json || !snap.system_conf) return;
  if (saveAllTimer) clearTimeout(saveAllTimer);
  saveAllTimer = setTimeout(async () => {
    saveAllTimer = null;
    try {
      const mergedConfig = mergeUiPatchIntoBackendConfig(snap.config_json, configStore.config);
      await apiSaveAllConfig(configStore.backend.http_base, {
        config_json: mergedConfig,
        system_conf: snap.system_conf
      });
      pushUiEvent("success", "全量配置同步", reasonKey ? `字段: ${reasonKey}` : "已调用 /api/config/all");
    } catch (e) {
      pushUiEvent("error", "全量配置同步失败", String(e?.message || e));
    }
  }, 800);
}

function setShared(k, v) {
  configStore.patchShared({ [k]: v });
  if (k === "active_audio_system_id") systemStore.setActiveAudioSystem(v);

  if (AUTO_SUBMIT_SHARED_KEYS.has(k)) scheduleBackendSubmit(k);
  scheduleBackendSaveAll(k);

  const keysToLog = [
    "active_audio_system_id",
    "realtime_audio_enabled",
    "ptt_enabled",
    "wake_enabled",
    "wake_word",
    "interrupt_enabled",
    "interrupt_mode",
    "autoplay_enabled",
    "qa_autoplay_enabled",
    "stt_enabled",
    "stt_engine",
    "stt_language",
    "stt_sample_rate",
    "tts_enabled",
    "tts_engine",
    "tts_rate",
    "tts_volume",
    "image_input_enabled"
  ];
  if (keysToLog.includes(k)) {
    pushUiEvent("info", "配置变更", `${k} = ${typeof v === "boolean" ? (v ? "开" : "关") : String(v)}`, { key: k, value: v });
  }
}

function setRealtimeAudioEnabled(v) {
  setShared("stt_enabled", !!v);
  setShared("realtime_audio_enabled", !!v);
  pushUiEvent("info", "实时音频", `录音已${v ? "开启" : "关闭"}`, { enabled: !!v });
}

function setAppearance(k, v) {
  configStore.patchAppearance({ [k]: v });
  if (APPEARANCE_CONTINUOUS_KEYS.has(k)) {
    pendingAppearanceLog = { key: k, value: v };
    if (appearanceEventTimer) clearTimeout(appearanceEventTimer);
    appearanceEventTimer = setTimeout(() => {
      appearanceEventTimer = null;
      const evt = pendingAppearanceLog;
      pendingAppearanceLog = null;
      if (!evt) return;
      try {
        console.info("[UI][appearance]", `${evt.key}=${String(evt.value)}`);
      } catch {}
      pushUiEvent("info", "外观", `${evt.key} = ${String(evt.value)}`, { key: evt.key, value: evt.value });
    }, 120);
    return;
  }
  try {
    console.info("[UI][appearance]", `${k}=${String(v)}`);
  } catch {}
  pushUiEvent("info", "外观", `${k} = ${String(v)}`, { key: k, value: v });
}

function cycleDopaminePalette() {
  const current = Math.max(0, Math.floor(Number(configStore.appearance.colorway_variant) || 0));
  const next = (current + 1) % DOPAMINE_PALETTE_COUNT;
  if (configStore.appearance.colorway_mode !== "dopamine202") {
    configStore.patchAppearance({ colorway_mode: "dopamine202" });
  }
  setAppearance("colorway_variant", next);
}

onBeforeUnmount(() => {
  if (appearanceEventTimer) clearTimeout(appearanceEventTimer);
  appearanceEventTimer = null;
  pendingAppearanceLog = null;
});

function setBackend(k, v) {
  configStore.patchBackend({ [k]: v });
  pushUiEvent("info", "后端连接", `${k} = ${String(v)}`, { key: k, value: v });
}

function pickBackground() {
  bgFileInput.value?.click?.();
}

async function onPickedBackground(e) {
  const file = e?.target?.files?.[0];
  if (!file) return;
  e.target.value = "";

  const maxBytes = 1.5 * 1024 * 1024;
  if (file.size > maxBytes) {
    pushUiEvent("warning", "背景上传失败", "图片太大（建议 <= 1.5MB）");
    return;
  }

  const ok = await idbSet("background_image", file);
  if (!ok) {
    pushUiEvent("error", "背景保存失败", "IndexedDB 写入失败（可能被浏览器策略拦截）。");
    return;
  }

  configStore.patchAppearance({
    background_enabled: true,
    background_rev: (configStore.appearance.background_rev || 0) + 1
  });
  pushUiEvent("success", "背景已更新", `已保存：${file.name}`);
}

async function clearBackground() {
  await idbDel("background_image");
  configStore.patchAppearance({
    background_enabled: false,
    background_rev: (configStore.appearance.background_rev || 0) + 1
  });
  pushUiEvent("info", "背景已清除", "已恢复默认背景。" );
}

async function callWake() {
  try {
    await apiToWake(configStore.backend.http_base);
    pushUiEvent("success", "唤醒", "已调用 /to_wake");
  } catch (e) {
    pushUiEvent("error", "唤醒失败", String(e?.message || e));
  }
}

async function callInterrupt() {
  try {
    await apiToStopTalking(configStore.backend.http_base);
    pushUiEvent("success", "打断", "已调用 /to_stop_talking");
  } catch (e) {
    pushUiEvent("error", "打断失败", String(e?.message || e));
  }
}
</script>

<template>
  <div class="drawer panel">
    <header class="hdr">
      <div class="hdr-main">
        <div class="ttl">{{ sectionTitle }}</div>
        <div class="sub">
          <span class="tag">当前：{{ systemStore.currentSystem.name }}</span>
          <span class="tag tag-cyan">音频 active：{{ configStore.shared.active_audio_system_id }}</span>
        </div>
      </div>
      <div class="hdr-actions">
        <button class="px-btn" @click="router.push('/settings')">高级…</button>
        <button class="px-btn" @click="onClose">收起</button>
      </div>
    </header>

    <!-- 音频 -->
    <section v-if="uiStore.leftSection === 'audio'" class="sec">
      <div class="grid">
        <SettingRow title="音频主系统" desc="仅允许 active 系统“听/说”（后端对齐生效）。">
          <select class="px-select" :value="configStore.shared.active_audio_system_id" @change="(e) => setShared('active_audio_system_id', e.target.value)">
            <option v-for="s in systemStore.systems" :key="s.id" :value="s.id">{{ s.name }}</option>
          </select>
        </SettingRow>

        <SettingRow title="实时音频" desc="只控制录音开关，不关闭系统">
          <button class="toggle-switch" :class="{ on: configStore.shared.stt_enabled }" @click="setRealtimeAudioEnabled(!configStore.shared.stt_enabled)">
            <span class="toggle-knob"></span>
          </button>
        </SettingRow>

        <SettingRow title="唤醒" desc="对应日志里的“待唤醒/唤醒成功”。">
          <button class="toggle-switch" :class="{ on: configStore.shared.wake_enabled }" @click="setShared('wake_enabled', !configStore.shared.wake_enabled)">
            <span class="toggle-knob"></span>
          </button>
        </SettingRow>

        <SettingRow title="唤醒词" desc="从后端 config.source.wake_word 同步。">
          <input class="px-input" :value="configStore.shared.wake_word" @change="(e) => setShared('wake_word', e.target.value)" />
        </SettingRow>

        <SettingRow title="动态打断" desc="对应日志里的“智能打断”。">
          <button class="toggle-switch" :class="{ on: configStore.shared.interrupt_enabled }" @click="setShared('interrupt_enabled', !configStore.shared.interrupt_enabled)">
            <span class="toggle-knob"></span>
          </button>
        </SettingRow>

        <SettingRow title="打断模式" desc="barge_in / soft / off。">
          <select class="px-select" :value="configStore.shared.interrupt_mode" @change="(e) => setShared('interrupt_mode', e.target.value)">
            <option v-for="o in interruptModeOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </SettingRow>

        <SettingRow title="自动播放" desc="后端：source.automatic_player_status。">
          <button class="toggle-switch" :class="{ on: configStore.shared.autoplay_enabled }" @click="setShared('autoplay_enabled', !configStore.shared.autoplay_enabled)">
            <span class="toggle-knob"></span>
          </button>
        </SettingRow>

        <SettingRow title="QA 自动播放" desc="与日志里的 QA 服务对齐。">
          <button class="toggle-switch" :class="{ on: configStore.shared.qa_autoplay_enabled }" @click="setShared('qa_autoplay_enabled', !configStore.shared.qa_autoplay_enabled)">
            <span class="toggle-knob"></span>
          </button>
        </SettingRow>

        <div class="split"></div>

        <SettingRow title="ASR / STT" desc="第一版只做开关；设备列表来自 WS deviceList。">
          <button class="toggle-switch" :class="{ on: configStore.shared.stt_enabled }" @click="setShared('stt_enabled', !configStore.shared.stt_enabled)">
            <span class="toggle-knob"></span>
          </button>
        </SettingRow>

        <SettingRow title="STT 引擎" desc="whisper/funasr/sherpa/vosk 等。">
          <select class="px-select" :value="configStore.shared.stt_engine" @change="(e) => setShared('stt_engine', e.target.value)">
            <option v-for="o in sttEngineOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </SettingRow>

        <SettingRow title="输入设备" desc="由 WS deviceList 填充。">
          <select class="px-select" :value="configStore.shared.stt_device" @change="(e) => setShared('stt_device', e.target.value)">
            <option value="default">默认</option>
            <option v-for="d in backendStore.deviceList" :key="String(d)" :value="String(d)">{{ d }}</option>
          </select>
        </SettingRow>

        <SettingRow title="语言" desc="前两项。">
          <select class="px-select" :value="configStore.shared.stt_language" @change="(e) => setShared('stt_language', e.target.value)">
            <option v-for="o in langOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </SettingRow>

        <SettingRow title="采样率" desc="仅 16k/48k。">
          <select class="px-select" :value="configStore.shared.stt_sample_rate" @change="(e) => setShared('stt_sample_rate', Number(e.target.value))">
            <option v-for="o in sampleRateOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </SettingRow>

        <div class="split"></div>

        <SettingRow title="TTS" desc="音色列表来自 WS voiceList。">
          <button class="toggle-switch" :class="{ on: configStore.shared.tts_enabled }" @click="setShared('tts_enabled', !configStore.shared.tts_enabled)">
            <span class="toggle-knob"></span>
          </button>
        </SettingRow>

        <SettingRow title="TTS 引擎" desc="edge/ali/eleven 等。">
          <select class="px-select" :value="configStore.shared.tts_engine" @change="(e) => setShared('tts_engine', e.target.value)">
            <option v-for="o in ttsEngineOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
          </select>
        </SettingRow>

        <SettingRow title="音色" desc="由 WS voiceList 填充。">
          <select class="px-select" :value="configStore.shared.tts_voice" @change="(e) => setShared('tts_voice', e.target.value)">
            <option value="default">默认</option>
            <option v-for="v in backendStore.voiceList" :key="String(v.id || v)" :value="String(v.id || v)">{{ v.name || v.id || v }}</option>
          </select>
        </SettingRow>

        <SettingRow title="语速" desc="0.5x-2.0x">
          <PixelSlider
            :model-value="configStore.shared.tts_rate"
            :min="0.5"
            :max="2"
            :step="0.1"
            :format="(v) => `${Number(v).toFixed(1)}x`"
            @update:model-value="(v) => setShared('tts_rate', v)"
          />
        </SettingRow>

        <SettingRow title="音量" desc="0-100">
          <PixelSlider
            :model-value="configStore.shared.tts_volume"
            :min="0"
            :max="100"
            :step="1"
            :format="(v) => `${Math.round(Number(v))}%`"
            @update:model-value="(v) => setShared('tts_volume', v)"
          />
        </SettingRow>

        <SettingRow title="角色音色（后端）" desc="/api/tts/voices">
          <div class="ctrl-col">
            <input class="px-input" v-model="ttsSisiVoice" placeholder="sisi_voice_uri" />
            <input class="px-input" v-model="ttsLiuyeVoice" placeholder="liuye_voice_uri" />
            <div class="btn-row">
              <button class="px-btn" :disabled="apiBusy" @click="callGetTtsVoices">读取</button>
              <button class="px-btn" :disabled="apiBusy" @click="callSetTtsVoices">保存</button>
            </div>
          </div>
        </SettingRow>

        <div class="split"></div>

        <SettingRow title="唤醒/打断按钮" desc="直接调用后端接口（用于验证链路）。">
          <div class="btn-row">
            <button class="px-btn" @click="callWake">唤醒</button>
            <button class="px-btn" @click="callInterrupt">打断</button>
          </div>
        </SettingRow>

        <div class="tip">
          WS：{{ backendStore.wsConnected ? "已连接" : "未连接" }}（{{ backendStore.wsUrl || "—" }}）
          · liveState：{{ backendStore.liveState ?? "—" }} · deviceList：{{ backendStore.deviceList.length }} · voiceList：{{ backendStore.voiceList.length }}
        </div>
      </div>
    </section>

    <!-- 系统 -->
    <section v-else-if="uiStore.leftSection === 'system'" class="sec">
      <div class="tip">说明：Sisi / Liuye 的配置各自保存；共享资源（音频/ASR/TTS）在“音频”里。</div>

      <div class="grid">
        <SettingRow title="LLM Provider" desc="对齐后端字段。">
          <input class="px-input" :value="configStore.systemConfig(systemStore.currentSystemId).llm_provider" @change="(e) => setSys('llm_provider', e.target.value)" />
        </SettingRow>

        <SettingRow title="LLM Model" desc="对齐后端字段。">
          <input class="px-input" :value="configStore.systemConfig(systemStore.currentSystemId).llm_model" @change="(e) => setSys('llm_model', e.target.value)" />
        </SettingRow>

        <SettingRow title="记忆 / 工具 / MCP / Skills" desc="这里不是“只开关”；详情请进“高级…”。">
          <button class="px-btn" @click="router.push('/settings')">打开配置详情</button>
        </SettingRow>
      </div>

      <div class="block">
        <div class="block-title">系统提示词</div>
        <textarea
          class="px-textarea"
          v-model="promptDraft"
          rows="7"
          placeholder="写点系统设定/规则（先本地保存，后续对齐后端）。"
          @blur="setSys('system_prompt', promptDraft)"
        ></textarea>
      </div>
    </section>

    <!-- 工具 -->
    <section v-else-if="uiStore.leftSection === 'tools'" class="sec">
      <div class="grid">
        <SettingRow title="数据源" desc="连接 Flask + WS10003。">
          <select class="px-select" :value="configStore.backend.mode" @change="(e) => setBackend('mode', e.target.value)">
            <option value="real">后端</option>
          </select>
        </SettingRow>

        <SettingRow title="HTTP Base" desc="默认 http://127.0.0.1:5000">
          <input class="px-input" :value="configStore.backend.http_base" @change="(e) => setBackend('http_base', e.target.value)" />
        </SettingRow>

        <SettingRow title="WS URL" desc="默认 ws://127.0.0.1:10003">
          <input class="px-input" :value="configStore.backend.ws_url" @change="(e) => setBackend('ws_url', e.target.value)" />
        </SettingRow>

        <SettingRow title="MCP / Skills / 公会 / Agent" desc="这块先做配置详情页，先放在 /settings。">
          <button class="px-btn" @click="router.push('/settings')">去设置页</button>
        </SettingRow>

        <div class="split"></div>

        <SettingRow title="POST /api/get-data" desc="读取当前配置与音色。">
          <button class="px-btn" :disabled="apiBusy" @click="callGetData">获取</button>
        </SettingRow>

        <SettingRow title="POST /api/send" desc="发送用户文本。">
          <div class="ctrl-col">
            <input class="px-input" v-model="sendUsername" placeholder="username" />
            <input class="px-input" v-model="sendText" placeholder="msg" />
            <button class="px-btn" :disabled="apiBusy" @click="callSend">发送</button>
          </div>
        </SettingRow>

        <SettingRow title="POST /api/get-member-list" desc="获取成员列表。">
          <button class="px-btn" :disabled="apiBusy" @click="callGetMemberList">获取</button>
        </SettingRow>

        <SettingRow title="GET /api/browser-check" desc="浏览器兼容性检测。">
          <button class="px-btn" :disabled="apiBusy" @click="callBrowserCheck">检测</button>
        </SettingRow>

        <SettingRow title="POST /api/get-msg" desc="拉取历史（JSON）。">
          <div class="ctrl-col">
            <textarea class="px-textarea" v-model="getMsgPayload" rows="4"></textarea>
            <button class="px-btn" :disabled="apiBusy" @click="callGetMsg">请求</button>
          </div>
        </SettingRow>

        <SettingRow title="POST /api/adopt_msg" desc="采纳消息（JSON）。">
          <div class="ctrl-col">
            <textarea class="px-textarea" v-model="adoptMsgPayload" rows="3"></textarea>
            <button class="px-btn" :disabled="apiBusy" @click="callAdoptMsg">提交</button>
          </div>
        </SettingRow>

        <SettingRow title="POST /to_greet" desc="触发打招呼（JSON）。">
          <div class="ctrl-col">
            <textarea class="px-textarea" v-model="greetPayload" rows="3"></textarea>
            <button class="px-btn" :disabled="apiBusy" @click="callToGreet">触发</button>
          </div>
        </SettingRow>

        <SettingRow title="POST /transparent_pass" desc="透传输入（JSON）。">
          <div class="ctrl-col">
            <textarea class="px-textarea" v-model="transparentPayload" rows="3"></textarea>
            <button class="px-btn" :disabled="apiBusy" @click="callTransparentPass">透传</button>
          </div>
        </SettingRow>
      </div>

      <div class="block">
        <div class="block-title">接口结果</div>
        <pre class="api-log">{{ apiLog || "暂无" }}</pre>
      </div>
    </section>

    <!-- 日志 / 事件 -->
    <section v-else-if="uiStore.leftSection === 'logs' || uiStore.leftSection === 'events'" class="sec">
      <div class="filters">
        <select class="px-select" :value="eventStore.filterSystemId" @change="(e) => eventStore.setFilterSystem(e.target.value)">
          <option v-for="v in systemFilterOptions" :key="v" :value="v">
            {{ v === "current" ? "当前系统" : v === "all" ? "全部系统" : v }}
          </option>
        </select>
        <select class="px-select" :value="eventStore.filterKind" @change="(e) => eventStore.setFilterKind(e.target.value)">
          <option v-for="v in kindOptions" :key="v" :value="v">{{ v === "all" ? "全部类型" : v }}</option>
        </select>
        <button class="px-btn" @click="eventStore.clear">清空</button>
      </div>

      <div class="elist">
        <div v-for="e in visibleEvents" :key="e.id" class="evt" :data-level="e.level">
          <div class="evt-top">
            <span class="badge">{{ e.system_id }}</span>
            <span class="badge badge-weak">{{ e.kind }}</span>
            <span class="evt-title">{{ e.title || "事件" }}</span>
            <span class="evt-time">{{ e.created_at }}</span>
          </div>
          <div class="evt-msg">{{ e.message }}</div>
          <details v-if="e.payload && Object.keys(e.payload).length" class="evt-payload">
            <summary>payload</summary>
            <pre>{{ JSON.stringify(e.payload, null, 2) }}</pre>
          </details>
        </div>
      </div>
    </section>

    <!-- 外观 -->
    <section v-else-if="uiStore.leftSection === 'appearance'" class="sec">
      <div class="grid">
        <SettingRow title="Dock 模式" desc="auto：宽屏展开文字；窄屏仅图标。">
          <select class="px-select" :value="configStore.appearance.dock_mode" @change="(e) => setAppearance('dock_mode', e.target.value)">
            <option value="auto">自动</option>
            <option value="expand">始终展开</option>
            <option value="collapse">始终收起</option>
          </select>
        </SettingRow>

        <SettingRow title="配色模式" desc="default 保持当前风格；dopamine202 使用多巴胺渐变（seed 202）。">
          <select class="px-select" :value="configStore.appearance.colorway_mode" @change="(e) => setAppearance('colorway_mode', e.target.value)">
            <option value="default">默认（不变）</option>
            <option value="dopamine202">多巴胺渐变 202</option>
          </select>
        </SettingRow>

        <SettingRow title="配色轮换" desc="单击切换下一套奢风色盘（8 套循环）。">
          <div class="btn-row">
            <button class="px-btn" @click="cycleDopaminePalette">换一套配色</button>
            <span class="tag">#{{ (Number(configStore.appearance.colorway_variant || 0) % DOPAMINE_PALETTE_COUNT) + 1 }}</span>
          </div>
        </SettingRow>

        <SettingRow title="背景图" desc="上传后持久保存（IndexedDB）。">
          <div class="btn-row">
            <button class="px-btn" @click="pickBackground">上传…</button>
            <button class="px-btn" @click="clearBackground">清除</button>
          </div>
        </SettingRow>

        <SettingRow title="背景柔化" desc="0-18">
          <PixelSlider
            :model-value="configStore.appearance.background_blur"
            :min="0"
            :max="18"
            :step="0.1"
            :format="(v) => `${Number(v).toFixed(1)}px`"
            @update:model-value="(v) => setAppearance('background_blur', v)"
          />
        </SettingRow>
      </div>

      <div class="split"></div>

      <div class="grid">
        <SettingRow title="水墨笔触特效" desc="点击/按键生成笔触并渐隐（Canvas）。">
          <button class="toggle-switch" :class="{ on: configStore.appearance.inkfx_enabled }" @click="setAppearance('inkfx_enabled', !configStore.appearance.inkfx_enabled)">
            <span class="toggle-knob"></span>
          </button>
        </SettingRow>

        <SettingRow title="特效强度" desc="0.2-2.0">
          <PixelSlider
            :model-value="configStore.appearance.inkfx_intensity"
            :min="0.2"
            :max="2.0"
            :step="0.01"
            :format="(v) => `${Number(v).toFixed(2)}`"
            @update:model-value="(v) => setAppearance('inkfx_intensity', v)"
          />
        </SettingRow>

        <SettingRow title="键盘触发" desc="all=所有按键；hotkeys=R/T/E/Y；none=关闭。">
          <select class="px-select" :value="configStore.appearance.inkfx_keyboard_mode" @change="(e) => setAppearance('inkfx_keyboard_mode', e.target.value)">
            <option value="all">all</option>
            <option value="hotkeys">hotkeys</option>
            <option value="none">none</option>
          </select>
        </SettingRow>

        <SettingRow title="混合模式" desc="更暗：multiply；更亮：screen；更柔：overlay。">
          <select class="px-select" :value="configStore.appearance.inkfx_blend" @change="(e) => setAppearance('inkfx_blend', e.target.value)">
            <option value="multiply">multiply</option>
            <option value="overlay">overlay</option>
            <option value="screen">screen</option>
          </select>
        </SettingRow>
      </div>

      <input ref="bgFileInput" type="file" accept="image/*" style="display: none" @change="onPickedBackground" />
    </section>

    <!-- 角色 -->
    <section v-else-if="uiStore.leftSection === 'avatar'" class="sec">
      <CharacterPanel />
      <Live2DControls />
    </section>
  </div>
</template>

<style scoped>
.drawer {
  height: 100%;
  overflow: auto;
}

.hdr {
  position: sticky;
  top: 0;
  z-index: 3;
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 12px 10px;
  border-bottom: 1px solid var(--stroke);
  background: var(--ui-hdr-bg);
  backdrop-filter: blur(12px) saturate(1.3);
}

.hdr-main {
  min-width: 0;
}
.ttl {
  font-weight: 750;
  letter-spacing: 0.2px;
  color: var(--text-0);
}
.sub {
  margin-top: 6px;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-radius: 999px;
  border: 1px solid var(--ui-tag-border);
  background: var(--ui-tag-bg);
  font-size: 11px;
  color: var(--text-1);
}
.tag-cyan {
  border-color: var(--ui-tag-strong-border);
  color: var(--ui-tag-strong-color);
}
.hdr-actions {
  display: flex;
  gap: 8px;
  flex: 0 0 auto;
}

.sec {
  padding: 12px;
}

.grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.split {
  height: 1px;
  background: var(--stroke);
  opacity: 0.7;
  margin: 6px 4px;
}

.tip {
  margin-top: 10px;
  color: var(--text-1);
  font-size: 11px;
  line-height: 1.45;
}

.filters {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 10px;
}

.elist {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.evt {
  padding: 10px 10px;
  border: 1px solid var(--stroke);
  border-radius: 14px;
  background: var(--bg-card);
}
.evt[data-level="success"] {
  border-color: rgba(76, 217, 133, 0.45);
  background: rgba(38, 79, 58, 0.35);
}
.evt[data-level="warning"] {
  border-color: rgba(255, 196, 0, 0.5);
  background: rgba(102, 77, 0, 0.35);
}
.evt[data-level="error"] {
  border-color: rgba(255, 77, 79, 0.6);
  background: rgba(92, 35, 36, 0.35);
}
.evt[data-level="info"] {
  border-color: rgba(80, 160, 255, 0.45);
  background: rgba(30, 54, 92, 0.3);
}
.evt[data-level="debug"] {
  border-color: rgba(160, 160, 160, 0.35);
  background: rgba(60, 60, 60, 0.25);
}

.evt-top {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: space-between;
  flex-wrap: wrap;
}

.badge {
  padding: 2px 6px;
  border-radius: 999px;
  border: 1px solid var(--ui-tag-border);
  background: var(--ui-tag-bg);
  font-size: 11px;
  color: var(--text-1);
}
.badge-weak {
  opacity: 0.8;
}
.evt-title {
  font-weight: 650;
  flex: 1 1 auto;
  min-width: 120px;
  color: var(--text-0);
}
.evt-time {
  color: var(--text-2);
  font-size: 11px;
}
.evt-msg {
  margin-top: 8px;
  color: var(--text-0);
  white-space: pre-wrap;
  line-height: 1.45;
}
.evt-payload {
  margin-top: 8px;
}
.evt-payload summary {
  cursor: pointer;
  color: var(--text-2);
}
.evt-payload pre {
  margin: 8px 0 0;
  padding: 10px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.2);
  color: var(--text-1);
  overflow: auto;
  font-size: 11px;
}

.block {
  margin-top: 12px;
}
.block-title {
  font-weight: 700;
  margin-bottom: 8px;
  color: var(--text-0);
}

.ctrl-col {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: min(420px, 100%);
}

.api-log {
  margin-top: 8px;
  padding: 10px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.2);
  color: var(--text-1);
  font-size: 12px;
  line-height: 1.45;
  white-space: pre-wrap;
  word-break: break-word;
}

.btn-row {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
}
</style>



