<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import SettingRow from "../components/SettingRow.vue";
import { useEventStore, EVENT_KINDS } from "../stores/eventStore";
import { useSystemStore } from "../stores/systemStore";

const router = useRouter();
const eventStore = useEventStore();
const systemStore = useSystemStore();

const systemOptions = computed(() => [
  { label: "当前系统", value: "current" },
  { label: "全部系统", value: "all" },
  ...systemStore.systems.map((s) => ({ label: s.name, value: s.id }))
]);

const kindOptions = computed(() => [{ label: "全部类型", value: "all" }, ...EVENT_KINDS.map((k) => ({ label: k, value: k }))]);

const visible = computed(() => {
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
</script>

<template>
  <div class="app-shell">
    <div class="bg-grid"></div>
    <div class="bg-scanline"></div>

    <div class="topbar">
      <div class="brand">
        <span class="brand-dot"></span>
        <span>事件时间线</span>
      </div>
      <div class="top-actions">
        <button class="px-btn" @click="router.push('/')">返回</button>
        <button class="px-btn" @click="eventStore.clear()">清空</button>
      </div>
    </div>

    <div class="page">
      <div class="panel body">
        <div class="grid">
          <SettingRow title="系统过滤" desc="current=当前，all=全部">
            <select class="px-select" :value="eventStore.filterSystemId" @change="(e) => eventStore.setFilterSystem(e.target.value)">
              <option v-for="o in systemOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </SettingRow>
          <SettingRow title="类型过滤" desc="all=全部">
            <select class="px-select" :value="eventStore.filterKind" @change="(e) => eventStore.setFilterKind(e.target.value)">
              <option v-for="o in kindOptions" :key="o.value" :value="o.value">{{ o.label }}</option>
            </select>
          </SettingRow>
        </div>

        <div class="list">
          <div v-if="!visible.length" class="tip">暂无事件。</div>
          <div v-for="e in visible" :key="e.id" class="item" :data-level="e.level">
            <div class="head">
              <span class="chip">{{ e.system_id }}</span>
              <span class="chip chip-dim">{{ e.kind }}</span>
              <span class="ttl">{{ e.title || "事件" }}</span>
              <span class="time">{{ e.created_at }}</span>
            </div>
            <div class="msg">{{ e.message }}</div>
            <details v-if="e.payload && Object.keys(e.payload).length" class="det">
              <summary>payload</summary>
              <pre>{{ JSON.stringify(e.payload, null, 2) }}</pre>
            </details>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  height: 100%;
  min-height: 0;
  padding: 14px;
}

.body {
  height: calc(100dvh - var(--topbar-h) - 2 * var(--work-pad));
  padding: 12px;
  overflow: auto;
}

.grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.list {
  margin-top: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.tip {
  padding: 10px 10px;
  border: 1px dashed rgba(255, 255, 255, 0.16);
  border-radius: 12px;
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.5;
  background: rgba(0, 0, 0, 0.12);
}

.item {
  padding: 10px 10px;
  border-radius: 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  background: rgba(0, 0, 0, 0.16);
}
.item[data-level="success"] {
  border-color: rgba(76, 217, 133, 0.45);
  background: rgba(38, 79, 58, 0.35);
}
.item[data-level="warning"] {
  border-color: rgba(255, 196, 0, 0.5);
  background: rgba(102, 77, 0, 0.35);
}
.item[data-level="error"] {
  border-color: rgba(255, 77, 79, 0.6);
  background: rgba(92, 35, 36, 0.35);
}
.item[data-level="info"] {
  border-color: rgba(80, 160, 255, 0.45);
  background: rgba(30, 54, 92, 0.3);
}
.item[data-level="debug"] {
  border-color: rgba(160, 160, 160, 0.35);
  background: rgba(60, 60, 60, 0.25);
}

.head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.chip {
  height: 18px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid rgba(255, 255, 255, 0.12);
  background: rgba(255, 255, 255, 0.06);
  font-size: 11px;
  color: rgba(255, 255, 255, 0.72);
}
.chip-dim {
  opacity: 0.85;
}
.ttl {
  font-weight: 800;
  margin-right: auto;
}
.time {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.55);
}
.msg {
  margin-top: 6px;
  white-space: pre-wrap;
  color: rgba(255, 255, 255, 0.84);
  line-height: 1.45;
}
.det {
  margin-top: 6px;
}
.det summary {
  cursor: pointer;
  color: rgba(255, 255, 255, 0.62);
  font-size: 12px;
}
.det pre {
  margin: 8px 0 0;
  padding: 10px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.3);
  overflow: auto;
}
</style>
