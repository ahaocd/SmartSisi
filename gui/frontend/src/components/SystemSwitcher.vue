<script setup>
import { computed } from "vue";
import { useSystemStore } from "../stores/systemStore";
import { useConfigStore } from "../stores/configStore";
import { useEventStore } from "../stores/eventStore";
import { apiSetSystemMode } from "../api/sisiApi";

const systemStore = useSystemStore();
const configStore = useConfigStore();
const eventStore = useEventStore();

const warm = computed(() => systemStore.currentSystemId === "sisi");
const cold = computed(() => systemStore.currentSystemId === "liuye");

async function switchSystem(target) {
  if (!["sisi", "liuye"].includes(target)) return;
  const prev = systemStore.currentSystemId;
  if (prev === target) return;
  systemStore.setCurrentSystem(target);
  systemStore.setActiveAudioSystem(target);

  if (configStore.backend.mode !== "real") return;
  const base = configStore.backend.http_base;
  if (!base) return;
  try {
    await apiSetSystemMode(base, target);
  } catch (e) {
    systemStore.setCurrentSystem(prev);
    systemStore.setActiveAudioSystem(prev);
    eventStore.pushEvent({
      system_id: prev,
      kind: "status",
      level: "error",
      title: "系统切换失败",
      message: String(e?.message || e)
    });
  }
}
</script>

<template>
  <div class="seg" role="tablist" aria-label="系统切换">
    <button
      class="seg-btn seg-btn--warm"
      :class="{ active: warm }"
      @click="switchSystem('sisi')"
      title="柳思思系统"
    >
      <span class="dot dot-warm"></span>
      <span>柳思思</span>
    </button>
    <button
      class="seg-btn seg-btn--cold"
      :class="{ active: cold }"
      @click="switchSystem('liuye')"
      title="柳叶系统"
    >
      <span class="dot dot-cold"></span>
      <span>柳叶</span>
    </button>
  </div>
</template>

<style scoped>
.seg {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 0, 0, 0.2);
  box-shadow: 2px 2px 0 rgba(0, 0, 0, 0.3);
}

.seg-btn {
  height: 30px;
  padding: 0 12px;
  border-radius: 999px;
  border: 1px solid transparent;
  background: transparent;
  color: rgba(255, 255, 255, 0.75);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  transition: background 160ms ease, border-color 160ms ease, color 160ms ease;
}

.seg-btn:hover {
  background: rgba(255, 255, 255, 0.06);
}

.seg-btn.active {
  border-color: rgba(255, 255, 255, 0.18);
  color: rgba(255, 255, 255, 0.92);
}

.seg-btn--warm.active {
  background: rgba(255, 176, 122, 0.14);
  box-shadow: inset 0 0 0 1px rgba(255, 176, 122, 0.1);
}

.seg-btn--cold.active {
  background: rgba(127, 223, 255, 0.12);
  box-shadow: inset 0 0 0 1px rgba(127, 223, 255, 0.08);
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  box-shadow: 0 0 10px rgba(255, 255, 255, 0.08);
}
.dot-warm {
  background: rgba(255, 176, 122, 0.9);
}
.dot-cold {
  background: rgba(127, 223, 255, 0.9);
}
</style>

