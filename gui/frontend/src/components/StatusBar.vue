<script setup>
import { computed } from "vue";
import { useSystemStore } from "../stores/systemStore";

const systemStore = useSystemStore();
const agentStatus = computed(() => systemStore.agentStatusBySystem[systemStore.currentSystemId] || "idle");
const agentLabel = computed(() => {
  const s = agentStatus.value;
  if (s === "speaking") return "\u8bf4\u8bdd";
  if (s === "listening") return "\u8046\u542c";
  if (s === "thinking") return "\u601d\u8003";
  if (s === "wake_pending") return "\u5f85\u5524\u9192";
  return "\u7a7a\u95f2";
});

const agentColor = computed(() => {
  const s = agentStatus.value;
  if (s === "speaking") return "rgba(92,255,174,0.78)";
  if (s === "listening") return "rgba(127,223,255,0.78)";
  if (s === "thinking") return "rgba(255,211,107,0.78)";
  if (s === "wake_pending") return "rgba(182,204,227,0.72)";
  return "rgba(255,255,255,0.26)";
});
</script>

<template>
  <div class="statusbar">
    <span class="pill" :title="`状态：${agentStatus}`">
      <span class="dot" :style="{ background: agentColor }"></span>
      <span class="txt">{{ agentLabel }}</span>
    </span>
  </div>
</template>

<style scoped>
.statusbar {
  display: flex;
  align-items: center;
  min-width: 0;
}
.pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  height: 30px;
  padding: 0 10px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 0, 0, 0.2);
  color: rgba(255, 255, 255, 0.78);
  font-size: 12px;
  white-space: nowrap;
  box-shadow: 2px 2px 0 rgba(0, 0, 0, 0.3);
}
.dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  box-shadow: 0 0 10px rgba(255, 255, 255, 0.08);
}
.txt {
  line-height: 1;
  letter-spacing: 0.1px;
}
</style>
