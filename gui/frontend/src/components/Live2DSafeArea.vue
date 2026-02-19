<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useSystemStore } from "../stores/systemStore";
import { useBackendStore } from "../stores/backendStore";

const systemStore = useSystemStore();
const backendStore = useBackendStore();
const bubbleStyle = ref({ left: "0px", top: "0px" });
const bubbleVisible = ref(false);
const auraStyle = ref({ left: "0px", top: "0px", width: "120px", height: "170px" });
const auraVisible = ref(false);
const auraMode = ref("idle");

const agentStatus = computed(() => systemStore.agentStatusBySystem[systemStore.currentSystemId] || "idle");
const audioLevel = computed(() => backendStore.audioLevel || 0);
const isTtsSpeaking = computed(() => backendStore.audioPlaying && agentStatus.value === "speaking");
const displayState = computed(() => {
  if (backendStore.musicPlaying) return "music";
  const s = agentStatus.value;
  if (s === "speaking") return "speaking";
  if (s === "wake_pending") return "wake_pending";
  if (s === "listening") return "listening";
  if (s === "thinking") return "thinking";
  return "idle";
});
const bubbleText = computed(() => {
  const s = displayState.value;
  if (s === "music") return "唱歌中";
  if (s === "speaking") return "说话中";
  if (s === "listening") return "聆听中";
  if (s === "thinking") return "思考中";
  if (s === "wake_pending") return "待唤醒";
  if (s === "idle") return "空闲";
  return "空闲";
});

let observer = null;
let resizeObserver = null;
let timer = null;
let motionTimer = null;
let mouthRaf = 0;
let mouthActive = false;
let mouthStart = 0;
let mouthTarget = 0;
let mouthCurrent = 0;
let motionMode = "";
let lastReport = "";
let lastSafeRightLog = "";
let auraOffTimer = null;

function emitMouseEvent(target, type, x, y) {
  if (!target || typeof target.dispatchEvent !== "function") return false;
  try {
    return !!target.dispatchEvent(new MouseEvent(type, { clientX: x, clientY: y, bubbles: true, button: 0, buttons: 1 }));
  } catch {
    return false;
  }
}

function dispatchTap(kind = "body") {
  const canvas = document.getElementById("live2d");
  if (!canvas) return false;
  const rect = canvas.getBoundingClientRect();
  // Use slightly left-biased body tap coordinates to match common hit-area
  // configs in bundled models (including bilibili-live defaults).
  const x = rect.left + rect.width * (kind === "head" ? 0.5 : 0.43);
  const y = rect.top + rect.height * (kind === "head" ? 0.28 : 0.72);
  const waifu = document.getElementById("waifu");
  const targets = [canvas];
  if (waifu) targets.push(waifu);
  let dispatched = false;
  for (const target of targets) {
    dispatched = emitMouseEvent(target, "mousedown", x, y) || dispatched;
    dispatched = emitMouseEvent(target, "mouseup", x, y) || dispatched;
    dispatched = emitMouseEvent(target, "click", x, y) || dispatched;
  }
  if (!dispatched) {
    dispatched = emitMouseEvent(window, "mousedown", x, y) || dispatched;
    dispatched = emitMouseEvent(window, "mouseup", x, y) || dispatched;
  }
  return dispatched;
}

function setAuraState(active, mode = "speaking") {
  if (active) {
    if (auraOffTimer) clearTimeout(auraOffTimer);
    auraOffTimer = null;
    auraMode.value = mode;
    auraVisible.value = true;
    return;
  }
  if (auraOffTimer) clearTimeout(auraOffTimer);
  auraOffTimer = setTimeout(() => {
    auraOffTimer = null;
    auraVisible.value = false;
    auraMode.value = "idle";
  }, 360);
}

function reportState(label) {
  const next = `${label}|agent=${agentStatus.value}|audio=${backendStore.audioPlaying ? 1 : 0}|music=${backendStore.musicPlaying ? 1 : 0}`;
  if (next === lastReport) return;
  lastReport = next;
  try {
    document.documentElement.dataset.live2dMotion = label;
    document.documentElement.dataset.live2dAgent = agentStatus.value || "idle";
    document.documentElement.dataset.live2dAudio = backendStore.audioPlaying ? "1" : "0";
    document.documentElement.dataset.live2dMusic = backendStore.musicPlaying ? "1" : "0";
  } catch {}
  try {
    console.info("[Live2D]", next);
  } catch {}
}

function setSleepy(on) {
  try {
    sessionStorage.setItem("Sleepy", on ? "1" : "0");
  } catch {}
}

function setMouthValue(v) {
  try {
    const next = Math.max(0, Math.min(1, Number(v) || 0));
    window.__live2dMouthValue = next;
  } catch {}
}

function normalizeMouthLevel(v) {
  const raw = Math.max(0, Math.min(1, Number(v) || 0));
  if (raw <= 0) return 0;
  // Boost low-volume speech so mouth movement remains visible.
  const boosted = Math.pow(raw, 0.65) * 1.35;
  return Math.max(0.18, Math.min(1, boosted));
}

function setMouthTargetLevel(v) {
  const next = normalizeMouthLevel(v);
  mouthTarget = next;
}

function mouthTick(ts) {
  if (!mouthActive) return;
  const now = ts || performance.now();
  if (!mouthStart) mouthStart = now;
  let target = mouthTarget;
  // Step 1: remove synthetic pulse fallback.
  // Mouth should only follow backend audio level during explicit playback window.
  mouthCurrent += (target - mouthCurrent) * 0.42;
  setMouthValue(mouthCurrent);
  mouthRaf = requestAnimationFrame(mouthTick);
}

function startMouthLoop() {
  if (mouthActive) return;
  mouthActive = true;
  mouthStart = 0;
  mouthTarget = 0;
  mouthCurrent = 0;
  mouthRaf = requestAnimationFrame(mouthTick);
}

function stopMouthLoop() {
  mouthActive = false;
  if (mouthRaf) cancelAnimationFrame(mouthRaf);
  mouthRaf = 0;
  mouthStart = 0;
  mouthTarget = 0;
  mouthCurrent = 0;
  setMouthValue(0);
}

function stopMotionLoop() {
  if (motionTimer) clearInterval(motionTimer);
  motionTimer = null;
  motionMode = "";
  reportState("stop");
}

function startMotionLoop(type) {
  if (motionMode === type && motionTimer) return;
  stopMotionLoop();
  motionMode = type;
  const interval = type === "music" ? 920 : 1150;
  const primaryTapKind = type === "music" ? "head" : "body";
  const secondaryTapKind = primaryTapKind === "head" ? "body" : "head";
  const fireTap = () => {
    const ok = dispatchTap(primaryTapKind);
    if (!ok) dispatchTap(secondaryTapKind);
  };
  fireTap();
  motionTimer = setInterval(fireTap, interval);
  reportState(type);
}

function setVar(px) {
  try {
    document.documentElement.style.setProperty("--live2d-safe-right", `${Math.max(0, Math.round(px || 0))}px`);
  } catch {}
}

function compute() {
  const waifu = document.querySelector(".waifu") || document.getElementById("waifu");
  const chatPanel = document.querySelector(".panel.chat");
  const composer = document.querySelector(".composer");
  if (!waifu || !chatPanel || !composer) {
    bubbleVisible.value = false;
    auraVisible.value = false;
    return setVar(0);
  }

  const waifuRect = waifu.getBoundingClientRect();
  const chatRect = chatPanel.getBoundingClientRect();
  const compRect = composer.getBoundingClientRect();

  function overlapY(a, b) {
    return Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
  }
  function overlapRight(rect) {
    const y = overlapY(waifuRect, rect);
    if (y <= 8) return 0;
    const x = rect.right - waifuRect.left;
    return x > 0 ? x : 0;
  }
  const reserve = Math.max(overlapRight(chatRect), overlapRight(compRect));
  const safeRight = reserve > 0 ? reserve + 24 : 0;
  setVar(safeRight);
  const nextSafeRightLog = [
    `safe=${Math.round(safeRight)}`,
    `reserve=${Math.round(reserve)}`,
    `waifuLeft=${Math.round(waifuRect.left)}`,
    `chatRight=${Math.round(chatRect.right)}`,
    `composerRight=${Math.round(compRect.right)}`
  ].join("|");
  if (nextSafeRightLog !== lastSafeRightLog) {
    lastSafeRightLog = nextSafeRightLog;
    try {
      console.info("[Live2D][safe-right]", nextSafeRightLog);
    } catch {}
  }

  const bubbleW = 74;
  const bubbleH = 28;
  const targetX = waifuRect.left - bubbleW * 0.6;
  const targetY = waifuRect.top + waifuRect.height * 0.45;
  const x = Math.min(window.innerWidth - bubbleW - 8, Math.max(8, targetX));
  const y = Math.min(window.innerHeight - bubbleH - 8, Math.max(8, targetY));
  bubbleStyle.value = { left: `${Math.round(x)}px`, top: `${Math.round(y)}px` };
  bubbleVisible.value = true;

  const auraW = Math.max(120, Math.round(waifuRect.width * 0.66));
  const auraH = Math.max(170, Math.round(waifuRect.height * 0.58));
  const auraX = Math.min(window.innerWidth - auraW - 6, Math.max(6, waifuRect.left + (waifuRect.width - auraW) * 0.5));
  const auraY = Math.min(window.innerHeight - auraH - 6, Math.max(6, waifuRect.top + waifuRect.height * 0.3));
  auraStyle.value = {
    left: `${Math.round(auraX)}px`,
    top: `${Math.round(auraY)}px`,
    width: `${Math.round(auraW)}px`,
    height: `${Math.round(auraH)}px`
  };

  try {
    const toolW = 44;
    const toolH = 120;
    const toolTargetX = waifuRect.right + 8;
    const toolTargetY = waifuRect.top + waifuRect.height * 0.35;
    const tx = Math.min(window.innerWidth - toolW - 8, Math.max(8, toolTargetX));
    const ty = Math.min(window.innerHeight - toolH - 8, Math.max(8, toolTargetY));
    document.documentElement.style.setProperty("--waifu-tool-x", `${Math.round(tx)}px`);
    document.documentElement.style.setProperty("--waifu-tool-y", `${Math.round(ty)}px`);
    document.documentElement.style.setProperty("--waifu-tool-scale", "0.85");
  } catch {}
}

function attachToWaifu() {
  const waifu = document.querySelector(".waifu") || document.getElementById("waifu");
  if (!waifu) return false;
  try {
    resizeObserver?.disconnect?.();
    resizeObserver = new ResizeObserver(() => compute());
    resizeObserver.observe(waifu);
  } catch {}
  compute();
  return true;
}

onMounted(() => {
  setVar(0);

  // Observe DOM for live2d-widget insertion.
  try {
    observer = new MutationObserver(() => {
      if (attachToWaifu()) return;
      compute();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
  } catch {}

  // Fallback polling (widget loads from CDN).
  timer = setInterval(() => {
    attachToWaifu();
  }, 800);

  window.addEventListener("resize", compute);
});

onBeforeUnmount(() => {
  try {
    observer?.disconnect?.();
    resizeObserver?.disconnect?.();
  } catch {}
  observer = null;
  resizeObserver = null;

  try {
    if (timer) clearInterval(timer);
  } catch {}
  timer = null;
  if (auraOffTimer) clearTimeout(auraOffTimer);
  auraOffTimer = null;
  auraVisible.value = false;
  stopMotionLoop();
  stopMouthLoop();

  window.removeEventListener("resize", compute);
  setVar(0);
});

watch(
  () => [systemStore.currentSystemId, agentStatus.value],
  () => {
    compute();
  }
);

watch(
  () => [agentStatus.value, backendStore.audioPlaying, backendStore.musicPlaying],
  () => {
    if (backendStore.musicPlaying) {
      setSleepy(false);
      setAuraState(true, "music");
      startMotionLoop("music");
      return;
    }
    if (agentStatus.value === "speaking" && backendStore.audioPlaying) {
      setSleepy(false);
      setAuraState(true, "speaking");
      startMotionLoop("speaking");
      return;
    }
    stopMotionLoop();
    if (agentStatus.value === "thinking") {
      setSleepy(true);
      setAuraState(false);
      reportState("thinking");
      return;
    }
    setSleepy(false);
    if (agentStatus.value === "listening") {
      setAuraState(true, "listening");
      dispatchTap("head");
      reportState("listening");
      return;
    }
    if (agentStatus.value === "wake_pending") {
      setAuraState(false);
      reportState("wake_pending");
      return;
    }
    setAuraState(false);
    reportState("idle");
  },
  { immediate: true }
);

watch(
  () => audioLevel.value,
  (level) => {
    if (!isTtsSpeaking.value) {
      stopMouthLoop();
      return;
    }
    const v = Number(level) || 0;
    setMouthTargetLevel(v);
    startMouthLoop();
  },
  { immediate: true }
);

watch(
  () => [backendStore.audioPlaying, agentStatus.value],
  ([playing]) => {
    const ttsSpeaking = !!playing && agentStatus.value === "speaking";
    if (ttsSpeaking) {
      setMouthTargetLevel(audioLevel.value);
      startMouthLoop();
    } else {
      if ((Number(audioLevel.value) || 0) <= 0.002) stopMouthLoop();
    }
  },
  { immediate: true }
);
</script>

<template>
  <div v-if="auraVisible" class="live2d-aura" :class="`mode-${auraMode}`" :style="auraStyle" aria-hidden="true"></div>
  <div v-if="bubbleVisible" class="live2d-bubble" :class="`state-${displayState}`" :style="bubbleStyle" aria-hidden="true">
    {{ bubbleText }}
  </div>
</template>

<style scoped>
.live2d-aura {
  position: fixed;
  border-radius: 999px;
  pointer-events: none;
  z-index: 34;
  mix-blend-mode: screen;
  background:
    radial-gradient(ellipse at center, rgba(110, 214, 255, 0.28) 0%, rgba(110, 214, 255, 0.12) 42%, rgba(10, 15, 25, 0) 78%);
  box-shadow: 0 20px 42px rgba(60, 150, 205, 0.3), 0 12px 26px rgba(0, 0, 0, 0.28);
  animation: aura-pulse 1.35s ease-in-out infinite, aura-drift 1s ease-in-out infinite;
}

.live2d-aura.mode-speaking {
  background:
    radial-gradient(ellipse at center, rgba(104, 236, 255, 0.34) 0%, rgba(97, 191, 255, 0.17) 40%, rgba(10, 15, 25, 0) 78%);
  box-shadow: 0 24px 52px rgba(79, 181, 233, 0.36), 0 14px 28px rgba(0, 0, 0, 0.3);
}

.live2d-aura.mode-music {
  background:
    radial-gradient(ellipse at center, rgba(106, 255, 185, 0.34) 0%, rgba(76, 218, 255, 0.2) 38%, rgba(10, 15, 25, 0) 78%);
  box-shadow: 0 26px 58px rgba(71, 220, 195, 0.38), 0 16px 30px rgba(0, 0, 0, 0.32);
  animation-duration: 1.05s, 0.75s;
}

.live2d-aura.mode-listening {
  background:
    radial-gradient(ellipse at center, rgba(157, 220, 255, 0.26) 0%, rgba(157, 220, 255, 0.1) 42%, rgba(10, 15, 25, 0) 80%);
  box-shadow: 0 18px 38px rgba(97, 158, 199, 0.26), 0 8px 20px rgba(0, 0, 0, 0.22);
  animation-duration: 1.8s, 1.35s;
}

@keyframes aura-pulse {
  0% {
    opacity: 0.2;
    filter: saturate(0.95);
  }
  50% {
    opacity: 0.44;
    filter: saturate(1.16);
  }
  100% {
    opacity: 0.22;
    filter: saturate(1.02);
  }
}

@keyframes aura-drift {
  0% {
    transform: translate3d(0, 0, 0);
  }
  25% {
    transform: translate3d(-2px, 1px, 0);
  }
  50% {
    transform: translate3d(1px, -1px, 0);
  }
  75% {
    transform: translate3d(2px, 1px, 0);
  }
  100% {
    transform: translate3d(0, 0, 0);
  }
}

.live2d-bubble {
  position: fixed;
  min-width: 72px;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.12);
  border: 1px solid rgba(255, 255, 255, 0.2);
  color: rgba(255, 255, 255, 0.9);
  display: grid;
  place-items: center;
  font-size: 12px;
  letter-spacing: 0.1px;
  pointer-events: none;
  z-index: 45;
  backdrop-filter: blur(6px) saturate(1.2);
  box-shadow: 0 10px 22px rgba(0, 0, 0, 0.25);
  white-space: nowrap;
}

.live2d-bubble.state-idle {
  background: rgba(182, 204, 227, 0.1);
  border-color: rgba(182, 204, 227, 0.26);
}

.live2d-bubble.state-wake_pending {
  background: rgba(182, 204, 227, 0.14);
  border-color: rgba(182, 204, 227, 0.34);
}

.live2d-bubble.state-listening {
  background: rgba(126, 214, 255, 0.2);
  border-color: rgba(126, 214, 255, 0.38);
}

.live2d-bubble.state-thinking {
  background: rgba(255, 214, 138, 0.2);
  border-color: rgba(255, 214, 138, 0.38);
}

.live2d-bubble.state-speaking {
  background: rgba(121, 255, 186, 0.2);
  border-color: rgba(121, 255, 186, 0.38);
}

.live2d-bubble.state-music {
  background: rgba(120, 242, 255, 0.24);
  border-color: rgba(120, 242, 255, 0.42);
}
</style>

