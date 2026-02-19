<script setup>
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useSystemStore } from "../stores/systemStore";
import { useBackendStore } from "../stores/backendStore";

const props = defineProps({
  traceId: { type: String, default: "" },
  placeholder: { type: Boolean, default: false },
  variant: { type: String, default: "bars" },
  messageId: { type: String, default: "" }
});

const systemStore = useSystemStore();
const backendStore = useBackendStore();
const currentSystemId = computed(() => systemStore.currentSystemId);
const agentStatus = computed(() => systemStore.agentStatusBySystem?.[currentSystemId.value] || "idle");
const openStreamMessageId = computed(() => systemStore.openStreamMessageIdBySystem?.[currentSystemId.value] || null);
const messageObj = computed(() => {
  if (!props.messageId) return null;
  const list = systemStore.messagesBySystem[currentSystemId.value] || [];
  return list.find((m) => m.id === props.messageId) || null;
});
const lastAssistantId = computed(() => {
  const list = systemStore.messagesBySystem[currentSystemId.value] || [];
  for (let i = list.length - 1; i >= 0; i -= 1) {
    if (list[i]?.role === "assistant") return list[i]?.id || null;
  }
  return null;
});

function withBaseUrl(p) {
  const base = String(import.meta.env.BASE_URL || "/");
  const normalizedBase = base.endsWith("/") ? base : `${base}/`;
  const normalizedPath = String(p || "").replace(/^\/+/, "");
  return `${normalizedBase}${normalizedPath}`;
}

// Is THIS message actively associated with current output?
// Rule: only explicit stream ownership / placeholder can activate.
const isActiveMessage = computed(() => {
  if (props.placeholder) return true;
  if (!props.messageId) return false;

  if (openStreamMessageId.value) {
    return openStreamMessageId.value === props.messageId;
  }

  const msg = messageObj.value;
  if (msg?.meta?.pending_reply || msg?.meta?.stream_open) return true;

  // Keep TTS/Music tail bound to the latest assistant bubble only while playback is active.
  if (backendStore.audioPlaying && agentStatus.value === "speaking") {
    return props.messageId === lastAssistantId.value;
  }
  if (backendStore.musicPlaying) {
    return props.messageId === lastAssistantId.value;
  }

  return false;
});

// Flow icons
const ICONS = {
  stt: { type: "img", value: withBaseUrl("icons/flow-stt.svg") },
  llm: { type: "img", value: withBaseUrl("icons/flow-llm.svg") },
  tts: { type: "img", value: withBaseUrl("icons/flow-tts.ico") },
  music: { type: "img", value: withBaseUrl("icons/flow-music.svg") },
  tool: {
    type: "svg",
    value:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.106-3.105c.32-.322.863-.22.983.218a6 6 0 0 1-8.259 7.057l-7.91 7.91a1 1 0 0 1-2.999-3l7.91-7.91a6 6 0 0 1 7.057-8.259c.438.12.54.662.219.984z"/></svg>'
  },
  mcp: {
    type: "svg",
    value:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z"/><path d="M12 22V12"/><polyline points="3.29 7 12 12 20.71 7"/><path d="m7.5 4.27 9 5.15"/></svg>'
  },
  skills: {
    type: "svg",
    value:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z"/><path d="M20 2v4"/><path d="M22 4h-4"/><circle cx="4" cy="20" r="2"/></svg>'
  },
  guild: {
    type: "svg",
    value:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z"/></svg>'
  },
  agent: {
    type: "svg",
    value:
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2"/><path d="M20 14h2"/><path d="M15 13v2"/><path d="M9 13v2"/></svg>'
  }
};

const STAGE_LABELS = {
  stt: "STT",
  llm: "LLM",
  tts: "TTS",
  music: "Music",
  tool: "Tool",
  mcp: "MCP",
  skills: "Skills",
  guild: "Guild",
  agent: "Agent"
};

const STAGE_MOTION = {
  stt: { peak: 1.08, rx: 2.2, ry: 1.2, dur: 1600, delay: -220, minScale: 0.9, glow: "rgba(124, 221, 255, 0.24)" },
  llm: { peak: 1.16, rx: 2.8, ry: 1.8, dur: 1840, delay: -510, minScale: 0.88, glow: "rgba(255, 210, 126, 0.26)" },
  tts: { peak: 1.24, rx: 3.6, ry: 1.6, dur: 1220, delay: -320, minScale: 0.9, glow: "rgba(126, 255, 188, 0.26)" },
  music: { peak: 1.2, rx: 4.2, ry: 2.3, dur: 980, delay: -460, minScale: 0.86, glow: "rgba(104, 243, 255, 0.3)" },
  tool: { peak: 1.14, rx: 2.5, ry: 1.4, dur: 1420, delay: -160, minScale: 0.9, glow: "rgba(185, 201, 255, 0.24)" },
  mcp: { peak: 1.12, rx: 2.6, ry: 1.5, dur: 1360, delay: -380, minScale: 0.9, glow: "rgba(170, 232, 255, 0.24)" },
  skills: { peak: 1.1, rx: 2.2, ry: 1.4, dur: 1540, delay: -240, minScale: 0.9, glow: "rgba(255, 223, 161, 0.24)" },
  guild: { peak: 1.09, rx: 2.1, ry: 1.1, dur: 1710, delay: -620, minScale: 0.91, glow: "rgba(193, 234, 255, 0.22)" },
  agent: { peak: 1.18, rx: 3.1, ry: 1.9, dur: 1280, delay: -410, minScale: 0.88, glow: "rgba(255, 193, 238, 0.26)" }
};
const PEAK_BOOST = 1.2; // +20%
const CLOSE_OUT_MS = 520;

function stageMotionStyle(stage) {
  const cfg = STAGE_MOTION[stage?.key] || STAGE_MOTION.llm;
  const base = Number(cfg.peak || 1.12);
  const finishPeak = Math.max(1.05, base * PEAK_BOOST);
  const runPeak = Math.max(1.03, 1 + (finishPeak - 1) * 0.62);
  return {
    "--run-peak": runPeak.toFixed(3),
    "--finish-peak": finishPeak.toFixed(3),
    "--orbit-rx": `${Number(cfg.rx || 2.8).toFixed(2)}px`,
    "--orbit-rx-neg": `${Number(-Math.abs(cfg.rx || 2.8)).toFixed(2)}px`,
    "--orbit-ry": `${Number(Math.abs(cfg.ry || 1.6)).toFixed(2)}px`,
    "--orbit-ry-neg": `${Number(-Math.abs(cfg.ry || 1.6)).toFixed(2)}px`,
    "--orbit-duration": `${Math.max(760, Number(cfg.dur || 1500))}ms`,
    "--orbit-delay": `${Number(cfg.delay || 0)}ms`,
    "--orbit-min-scale": Number(cfg.minScale || 0.9).toFixed(3),
    "--stage-glow": String(cfg.glow || "rgba(140, 220, 255, 0.2)")
  };
}

function iconIsImg(key) {
  return ICONS[key]?.type === "img";
}

function iconSrc(key) {
  return ICONS[key]?.value || "";
}

function iconSvg(key) {
  return ICONS[key]?.value || "";
}

// --- Timeline: accumulate icons as stages happen, keep history ---
// Each entry: { key, label, state, addedAt, updatedAt }
// state: "running" | "done" | "error"
const timeline = ref([]);
// Track what we've already seen so we don't re-add
const seen = ref(new Set());

function addStage(key, label, state) {
  const ts = Date.now();
  if (seen.value.has(key)) {
    // Update existing stage state
    const entry = timeline.value.find((e) => e.key === key);
    if (entry && entry.state !== state) {
      entry.state = state;
      entry.updatedAt = ts;
    }
    return;
  }
  seen.value.add(key);
  timeline.value.push({ key, label, state, addedAt: ts, updatedAt: ts });
}

function setDone(key) {
  const entry = timeline.value.find((e) => e.key === key);
  if (!entry) return;
  if (entry.state !== "done") {
    entry.state = "done";
  }
  entry.updatedAt = Date.now();
}

function setRunning(key, label = STAGE_LABELS[key] || String(key || "").toUpperCase()) {
  addStage(key, label, "running");
}

function finalizeRunningStages() {
  const ts = Date.now();
  for (const entry of timeline.value) {
    if (entry.state !== "running") continue;
    entry.state = "done";
    entry.updatedAt = ts;
  }
}

function clearTimeline() {
  timeline.value = [];
  seen.value = new Set();
  lastPhaseStage = "";
}

const isClosing = ref(false);
let closeTimer = null;

function clearCloseTimer() {
  if (closeTimer) clearTimeout(closeTimer);
  closeTimer = null;
}

function beginCloseOut() {
  if (!timeline.value.length) return;
  clearCloseTimer();
  isClosing.value = true;
  const ts = Date.now();
  for (const entry of timeline.value) {
    if (entry.state === "closing") continue;
    entry.state = "closing";
    entry.updatedAt = ts;
  }
  closeTimer = setTimeout(() => {
    closeTimer = null;
    isClosing.value = false;
    clearTimeline();
  }, CLOSE_OUT_MS);
}

// Watch agentStatus changes and drive timeline
watch(
  agentStatus,
  (status, oldStatus) => {
    if (!isActiveMessage.value) return;

    if (status === "listening") {
      setRunning("stt");
    }
    if (oldStatus === "listening" && status !== "listening") {
      setDone("stt");
    }

    if (status === "thinking") {
      setDone("stt");
      setRunning("llm");
    }

    if (status === "speaking") {
      setDone("llm");
      setRunning("tts");
    }

    if (oldStatus === "speaking" && status !== "speaking") {
      setDone("tts");
      setDone("music");
    }
  },
  { immediate: true }
);

// Watch stream_open: when text starts arriving, LLM is "done"
const hasContent = computed(() => !!String(messageObj.value?.content || "").trim());
const isStreamOpen = computed(() => !!messageObj.value?.meta?.stream_open);
const isPending = computed(() => !!messageObj.value?.meta?.pending_reply);
const messagePhase = computed(() => String(messageObj.value?.meta?.phase || "").toLowerCase());
const messageRawType = computed(() => String(messageObj.value?.meta?.raw_type || "").toLowerCase());

function resolveStageFromMeta(phase, rawType) {
  const p = String(phase || "").toLowerCase();
  const t = String(rawType || "").toLowerCase();
  const s = `${p} ${t}`.trim();
  if (!s) return "";

  const hasAny = (keys) => keys.some((k) => s.includes(k));

  if (hasAny(["mcp"])) return "mcp";
  if (hasAny(["skill", "skills"])) return "skills";
  if (hasAny(["guild", "adventurer"])) return "guild";
  if (hasAny(["tool", "tool_call", "toolcall", "function", "call"])) return "tool";
  if (hasAny(["agent", "coordinator"])) return "agent";
  if (hasAny(["music", "song", "player", "audio_music"])) return "music";
  if (hasAny(["tts", "speak", "voice", "audio_play"])) return "tts";
  if (hasAny(["think", "reason", "llm", "model"])) return "llm";
  return "";
}

const phaseStage = computed(() => resolveStageFromMeta(messagePhase.value, messageRawType.value));
let lastPhaseStage = "";

watch(
  hasContent,
  (has) => {
    if (!isActiveMessage.value) return;
    if (has) {
      // Text started appearing -> LLM produced output
      if (seen.value.has("llm")) setDone("llm");
      else addStage("llm", STAGE_LABELS.llm, "done");
    }
  }
);

// Watch audioPlaying -> TTS stage
watch(
  () => backendStore.audioPlaying,
  (playing) => {
    if (!isActiveMessage.value) return;
    if (playing) {
      setDone("llm");
      setRunning("tts");
    } else {
      setDone("tts");
    }
  }
);

// Watch musicPlaying -> Music stage
watch(
  () => backendStore.musicPlaying,
  (playing) => {
    if (!isActiveMessage.value) return;
    if (playing) {
      setRunning("music");
    } else {
      setDone("music");
    }
  }
);

// On placeholder (pending_reply with no content yet), show LLM spinning
watch(
  isPending,
  (pending) => {
    if (!isActiveMessage.value) return;
    if (pending && !hasContent.value) {
      setRunning("llm");
    }
  },
  { immediate: true }
);

watch(
  isActiveMessage,
  (active) => {
    if (active) return;
    // Once this bubble is no longer the active assistant message, close any
    // unresolved running stages so old icons don't hang forever.
    finalizeRunningStages();
    beginCloseOut();
  },
  { immediate: true }
);

watch(
  phaseStage,
  (stage) => {
    if (!isActiveMessage.value) return;
    if (!stage) {
      if (lastPhaseStage) setDone(lastPhaseStage);
      lastPhaseStage = "";
      return;
    }
    if (lastPhaseStage && lastPhaseStage !== stage) setDone(lastPhaseStage);
    if (stage !== "llm") setDone("llm");
    setRunning(stage, STAGE_LABELS[stage] || stage.toUpperCase());
    lastPhaseStage = stage;
  },
  { immediate: true }
);

watch(
  isStreamOpen,
  (open) => {
    if (open) return;
    // Stream closed -> settle the dynamic stages from this turn.
    if (lastPhaseStage) {
      setDone(lastPhaseStage);
      lastPhaseStage = "";
    }
    setDone("llm");
    if (!backendStore.audioPlaying) setDone("tts");
    if (!backendStore.musicPlaying) setDone("music");
  },
  { immediate: true }
);

const isOutputActive = computed(() => {
  if (!isActiveMessage.value) return false;
  if (props.placeholder) return true;
  if (isPending.value || isStreamOpen.value) return true;
  if (backendStore.audioPlaying || backendStore.musicPlaying) return true;
  return ["listening", "thinking", "speaking"].includes(agentStatus.value);
});

watch(
  isOutputActive,
  (active) => {
    if (active) {
      clearCloseTimer();
      if (isClosing.value) {
        isClosing.value = false;
        const ts = Date.now();
        for (const entry of timeline.value) {
          if (entry.state === "closing") {
            entry.state = "done";
            entry.updatedAt = ts;
          }
        }
      }
      return;
    }
    finalizeRunningStages();
    beginCloseOut();
  },
  { immediate: true }
);

onBeforeUnmount(() => {
  clearCloseTimer();
  closeTimer = null;
});

const visibleStages = computed(() => {
  return timeline.value;
});

const show = computed(() => visibleStages.value.length > 0 || isClosing.value);
const reserveSlot = ref(false);

watch(
  show,
  (visible) => {
    if (visible) reserveSlot.value = true;
  },
  { immediate: true }
);
</script>

<template>
  <Transition name="flowwrap">
    <div v-if="reserveSlot || show" class="flowwrap" :data-show="show ? '1' : '0'">
      <TransitionGroup name="flowstage" tag="div" class="flow" :data-variant="variant">
        <span
          v-for="s in visibleStages"
          :key="s.key"
          class="stage"
          :data-state="s.state"
          :data-key="s.key"
          :title="s.label"
          :style="stageMotionStyle(s)"
        >
          <span class="ico" v-if="iconIsImg(s.key)">
            <img :src="iconSrc(s.key)" alt="" />
          </span>
          <span v-else class="ico" v-html="iconSvg(s.key)"></span>
        </span>
      </TransitionGroup>
    </div>
  </Transition>
</template>

<style scoped>
.flowwrap {
  align-self: flex-start;
  margin-left: 0;
  margin-top: 4px;
  overflow: visible;
  min-height: 24px;
  transition: opacity 160ms ease;
}

.flowwrap[data-show="0"] {
  opacity: 0;
  pointer-events: none;
}

.flowwrap[data-show="1"] {
  opacity: 1;
}

.flow {
  display: flex;
  flex-wrap: nowrap;
  gap: 1px;
  align-items: center;
  min-height: 22px;
  overflow: visible;
}

.stage {
  height: 22px;
  width: 22px;
  padding: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 0;
  border: none;
  background: transparent;
  color: rgba(255, 255, 255, 0.9);
  position: relative;
  overflow: visible;
  box-shadow: none;
  opacity: 1;
  transition: opacity 140ms ease;
  --run-peak: 1.1;
  --finish-peak: 1.36;
  --orbit-rx: 2.8px;
  --orbit-rx-neg: -2.8px;
  --orbit-ry: 1.6px;
  --orbit-ry-neg: -1.6px;
  --orbit-duration: 1500ms;
  --orbit-delay: 0ms;
  --orbit-min-scale: 0.9;
  --stage-glow: rgba(140, 220, 255, 0.2);
}

.ico {
  width: 15px;
  height: 15px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.96);
  filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.55)) drop-shadow(0 0 9px var(--stage-glow))
    drop-shadow(0 0 0.8px rgba(172, 180, 196, 0.86));
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate3d(0, -50%, 0) scale(0.92);
  transform-origin: center;
  will-change: transform, opacity;
}
.ico img {
  width: 15px;
  height: 15px;
  display: block;
  border-radius: 3px;
}
.ico :deep(svg) {
  width: 15px;
  height: 15px;
  display: block;
  stroke: rgba(172, 180, 196, 0.86);
  stroke-width: 1.3;
  paint-order: stroke fill;
  vector-effect: non-scaling-stroke;
}

.stage[data-state="running"] {
  opacity: 1;
}

.stage[data-state="running"] .ico {
  animation: icon-orbit var(--orbit-duration) cubic-bezier(0.38, 0.02, 0.18, 1) var(--orbit-delay) infinite;
}

.stage[data-state="done"] {
  opacity: 1;
}

.stage[data-state="done"] .ico {
  animation: icon-done 360ms cubic-bezier(0.2, 0.82, 0.25, 1) both;
}

.stage[data-state="error"] {
  opacity: 1;
}

.stage[data-state="error"] .ico {
  animation: icon-close 560ms cubic-bezier(0.22, 0.88, 0.24, 1) forwards;
  filter: drop-shadow(0 1px 3px rgba(0, 0, 0, 0.55)) drop-shadow(0 0 10px rgba(255, 115, 115, 0.26));
}

.stage[data-state="closing"] .ico {
  animation: icon-close 560ms cubic-bezier(0.22, 0.88, 0.24, 1) forwards;
}

@keyframes icon-orbit {
  0% {
    transform: translate3d(var(--orbit-rx), -50%, 0) scale(var(--orbit-min-scale));
    opacity: 0.74;
  }
  25% {
    transform: translate3d(0, calc(-50% + var(--orbit-ry-neg)), 0) scale(1.02);
    opacity: 0.96;
  }
  50% {
    transform: translate3d(var(--orbit-rx-neg), -50%, 0) scale(var(--run-peak));
    opacity: 1;
  }
  75% {
    transform: translate3d(0, calc(-50% + var(--orbit-ry)), 0) scale(1.04);
    opacity: 0.94;
  }
  100% {
    transform: translate3d(var(--orbit-rx), -50%, 0) scale(var(--orbit-min-scale));
    opacity: 0.74;
  }
}

@keyframes icon-done {
  0% {
    transform: translate3d(0, -50%, 0) scale(1.02);
    opacity: 0.92;
  }
  50% {
    transform: translate3d(0, -50%, 0) scale(calc((var(--run-peak) - 1) * 0.65 + 1));
    opacity: 1;
  }
  100% {
    transform: translate3d(0, -50%, 0) scale(1);
    opacity: 0.96;
  }
}

@keyframes icon-close {
  0% {
    transform: translate3d(1px, -50%, 0) scale(1);
    opacity: 0.92;
  }
  56% {
    transform: translate3d(0, -50%, 0) scale(var(--finish-peak));
    opacity: 1;
  }
  100% {
    transform: translate3d(-4px, -50%, 0) scale(0.28);
    opacity: 0;
  }
}

.flowwrap-enter-active,
.flowwrap-leave-active {
  transition: opacity 150ms ease, transform 150ms ease;
}
.flowwrap-enter-from,
.flowwrap-leave-to {
  opacity: 0;
  transform: translateY(2px);
}

.flowstage-enter-active {
  animation: flow-slide-in 180ms ease;
}
.flowstage-leave-active {
  animation: flow-slide-out 140ms ease forwards;
}
.flowstage-enter-from {
  opacity: 0;
  transform: translateX(10px);
}
.flowstage-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}
.flowstage-move {
  transition: transform 130ms ease;
}

@keyframes flow-slide-in {
  0% {
    opacity: 0;
    transform: translateX(12px);
  }
  100% {
    opacity: 1;
    transform: translateX(0);
  }
}

@keyframes flow-slide-out {
  0% {
    opacity: 1;
    transform: translateX(0);
  }
  100% {
    opacity: 0;
    transform: translateX(-12px);
  }
}

@media (prefers-reduced-motion: reduce) {
  .flowwrap-enter-active,
  .flowwrap-leave-active,
  .flowstage-enter-active,
  .flowstage-leave-active,
  .flowstage-move {
    transition: none !important;
    animation: none !important;
  }
  .stage[data-state="running"] .ico {
    animation: none !important;
  }
}
</style>

