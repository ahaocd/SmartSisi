<script setup>
import { computed } from "vue";
import { NButton, NDrawer, NDrawerContent, NSelect, NTag } from "naive-ui";
import { useEventStore, EVENT_KINDS } from "../stores/eventStore";
import { useSystemStore } from "../stores/systemStore";

const eventStore = useEventStore();
const systemStore = useSystemStore();

const systemOptions = computed(() => [
  { label: "当前系统", value: "current" },
  { label: "全部系统", value: "all" },
  ...systemStore.systems.map((s) => ({ label: s.name, value: s.id }))
]);

const kindOptions = computed(() => [{ label: "全部类型", value: "all" }, ...EVENT_KINDS.map((k) => ({ label: k, value: k }))]);

const visibleEvents = computed(() => {
  const systemFilter = eventStore.filterSystemId;
  const kindFilter = eventStore.filterKind;
  const currentSystem = systemStore.currentSystemId;
  return eventStore.events.filter((e) => {
    if (systemFilter === "current" && e.system_id !== currentSystem) return false;
    if (systemFilter !== "current" && systemFilter !== "all" && e.system_id !== systemFilter) return false;
    if (kindFilter !== "all" && e.kind !== kindFilter) return false;
    return true;
  });
});

function levelTagType(level) {
  if (level === "success") return "success";
  if (level === "warning") return "warning";
  if (level === "error") return "error";
  return "info";
}
</script>

<template>
  <n-drawer v-model:show="eventStore.drawerOpen" width="420" placement="right">
    <n-drawer-content title="事件" closable>
      <div style="display: flex; gap: 10px; align-items: center; margin-bottom: 12px">
        <n-select
          size="small"
          :value="eventStore.filterSystemId"
          :options="systemOptions"
          style="min-width: 140px"
          @update:value="eventStore.setFilterSystem"
        />
        <n-select size="small" :value="eventStore.filterKind" :options="kindOptions" style="min-width: 140px" @update:value="eventStore.setFilterKind" />
        <n-button size="small" secondary @click="eventStore.closeDrawer">关闭</n-button>
      </div>

      <div style="display: flex; flex-direction: column; gap: 10px">
        <div
          v-for="e in visibleEvents"
          :key="e.id"
          style="padding: 10px 12px; border: 1px solid rgba(255,255,255,0.10); border-radius: 14px; background: rgba(255,255,255,0.04)"
        >
          <div style="display: flex; gap: 8px; align-items: center; justify-content: space-between">
            <div style="display: flex; gap: 8px; align-items: center">
              <n-tag size="tiny" type="info">{{ e.system_id }}</n-tag>
              <n-tag size="tiny" :type="levelTagType(e.level)">{{ e.kind }}</n-tag>
              <div style="font-weight: 650">{{ e.title || "事件" }}</div>
            </div>
            <div style="color: rgba(255,255,255,0.55); font-size: 12px">{{ e.created_at }}</div>
          </div>

          <div style="margin-top: 8px; color: rgba(255,255,255,0.8); white-space: pre-wrap; line-height: 1.45">{{ e.message }}</div>

          <details v-if="e.payload && Object.keys(e.payload).length" style="margin-top: 8px">
            <summary style="cursor: pointer; color: rgba(255,255,255,0.6)">payload</summary>
            <pre style="margin: 8px 0 0; padding: 10px; border-radius: 12px; background: rgba(0,0,0,0.28); overflow: auto">{{
              JSON.stringify(e.payload, null, 2)
            }}</pre>
          </details>
        </div>
      </div>
    </n-drawer-content>
  </n-drawer>
</template>
