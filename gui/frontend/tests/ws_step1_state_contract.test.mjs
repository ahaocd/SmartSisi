import assert from "node:assert/strict";
import fs from "node:fs";

const wsBridgePath = new URL("../src/api/wsBridge.js", import.meta.url);
const live2dPath = new URL("../src/components/Live2DSafeArea.vue", import.meta.url);
const recorderPath = new URL("../../../core/recorder.py", import.meta.url);

const wsBridge = fs.readFileSync(wsBridgePath, "utf8");
const live2d = fs.readFileSync(live2dPath, "utf8");
const recorder = fs.readFileSync(recorderPath, "utf8");

assert.equal(
  wsBridge.includes("noteAudioSignal(obj.audio_level)") || wsBridge.includes("noteAudioSignal(obj.audioLevel)"),
  false,
  "wsBridge must not infer audioPlaying from audio_level"
);

assert.equal(
  wsBridge.includes("updateStatusFromPanelMsg(systemStore, sid, obj.panelMsg, backendStore)"),
  false,
  "wsBridge must not infer agent status from panelMsg text"
);

assert.equal(
  wsBridge.includes("setSpeakingFromAudio(systemStore, backendStore, true)") || wsBridge.includes("setSpeakingFromAudio(systemStore, backendStore, false)"),
  false,
  "wsBridge must not back-write agent_status from frontend audioPlaying"
);

assert.equal(
  wsBridge.includes("const sid = systemStore.activeAudioSystemId || systemStore.currentSystemId;\n        const next = String(incomingAgentStatus || \"\").toLowerCase();"),
  false,
  "incoming agent_status must map to currentSystemId only"
);

assert.equal(
  wsBridge.includes("[\"idle\", \"wake_pending\", \"listening\", \"thinking\", \"speaking\"].includes(next)"),
  true,
  "wsBridge must accept wake_pending from backend agent_status"
);

assert.equal(
  wsBridge.includes("const isBareListening = next === \"listening\" && !hasPanelMsgText;"),
  true,
  "wsBridge must ignore bare listening status updates without panelMsg"
);

assert.equal(
  live2d.includes("if (backendStore.audioPlaying && target <= 0.01)"),
  false,
  "Live2D mouth fallback pulse must be disabled"
);

assert.equal(
  live2d.includes("if (s === \"wake_pending\") return \"待唤醒\";") ||
    live2d.includes("if (s === \"wake_pending\") return \"\\u5f85\\u5524\\u9192\";"),
  true,
  "Live2D bubble must map wake_pending => 待唤醒"
);

assert.equal(
  live2d.includes("if (s === \"idle\") return \"空闲\";") ||
    live2d.includes("if (s === \"idle\") return \"\\u7a7a\\u95f2\";"),
  true,
  "Live2D bubble must map idle => 空闲"
);

assert.equal(
  live2d.includes("if (backendStore.audioPlaying) return \"speaking\";"),
  false,
  "Live2D display state must not force speaking from audioPlaying alone"
);

assert.equal(
  live2d.includes("const isTtsSpeaking = computed(() => backendStore.audioPlaying && agentStatus.value === \"speaking\");"),
  true,
  "Live2D mouth/motion must gate by speaking+audioPlaying"
);

assert.equal(
  recorder.includes("\"panelMsg\": \"[!] 待唤醒！\", \"agent_status\": \"wake_pending\""),
  true,
  "recorder must emit wake_pending for 待唤醒"
);

assert.equal(
  recorder.includes("\"panelMsg\": \"[!] 待唤醒！\", \"agent_status\": \"idle\""),
  false,
  "recorder must not emit idle for 待唤醒"
);
