<script setup>
import { computed, ref } from "vue";
import { useSystemStore } from "../stores/systemStore";

const systemStore = useSystemStore();
const collapsed = ref(true);

const status = computed(() => systemStore.agentStatusBySystem[systemStore.currentSystemId] || "idle");

const mood = computed(() => {
  const s = status.value;
  if (s === "speaking") return { label: "speaking", color: "rgba(92,255,174,0.75)" };
  if (s === "listening") return { label: "listening", color: "rgba(127,223,255,0.75)" };
  if (s === "thinking") return { label: "thinking", color: "rgba(255,211,107,0.75)" };
  if (s === "wake_pending") return { label: "wake_pending", color: "rgba(182,204,227,0.72)" };
  return { label: "idle", color: "rgba(255,255,255,0.28)" };
});
</script>

<template>
  <div class="panel glow-border character">
    <div class="character-head">
      <div class="character-title">
        <div class="avatar-dot" :style="{ background: mood.color }"></div>
        <div style="display: flex; flex-direction: column; gap: 2px">
          <div style="font-weight: 800; letter-spacing: 0.2px">状态</div>
          <div class="character-sub">系统={{ systemStore.currentSystem.name }} · {{ mood.label }}</div>
        </div>
      </div>

      <button class="mini-btn" @click="collapsed = !collapsed">{{ collapsed ? "展开" : "收起" }}</button>
    </div>

    <div v-if="!collapsed" class="character-body">
      <div class="kv">
        <span class="k">音频 active</span>
        <span class="v">{{ systemStore.activeAudioSystemId }}</span>
      </div>
      <div class="kv">
        <span class="k">提示</span>
        <span class="v">流程条只在步骤发生时出现，完成后自动消失。</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.character {
  padding: 10px 12px;
}
.character-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.character-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}
.avatar-dot {
  width: 18px;
  height: 18px;
  border-radius: 7px;
  box-shadow: 0 14px 36px rgba(0, 0, 0, 0.35);
  border: 1px solid rgba(255, 255, 255, 0.14);
}
.character-sub {
  color: rgba(255, 255, 255, 0.62);
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mini-btn {
  height: 28px;
  padding: 0 10px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 0, 0, 0.22);
  color: rgba(255, 255, 255, 0.85);
  cursor: pointer;
}
.mini-btn:hover {
  border-color: rgba(255, 255, 255, 0.22);
}
.character-body {
  margin-top: 10px;
  display: grid;
  gap: 8px;
}
.kv {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12px;
}
.k {
  color: rgba(255, 255, 255, 0.58);
}
.v {
  color: rgba(255, 255, 255, 0.80);
}
</style>
