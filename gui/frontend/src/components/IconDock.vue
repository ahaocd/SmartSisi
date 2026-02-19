<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useUiStore } from "../stores/uiStore";
import { useConfigStore } from "../stores/configStore";
import { useMediaQuery } from "../ui/useMediaQuery";
import { getIcon } from "../ui/icons";

const uiStore = useUiStore();
const configStore = useConfigStore();

const items = computed(() => [
  { key: "audio", label: "音频", ico: "audio" },
  { key: "system", label: "系统", ico: "system" },
  { key: "tools", label: "工具", ico: "tools" },
  { key: "logs", label: "日志", ico: "logs" },
  { key: "appearance", label: "外观", ico: "appearance" },
  { key: "avatar", label: "角色", ico: "avatar" }
]);

const isWide = useMediaQuery("(min-width: 1100px)");
const expanded = computed(() => {
  const mode = configStore.appearance.dock_mode || "auto";
  if (mode === "expand") return true;
  if (mode === "collapse") return false;
  return !!isWide.value;
});

const dockWidth = computed(() => (expanded.value ? 150 : 56));
const dockEl = ref(null);

function iconHtml(kind, name) {
  return getIcon(kind, name, configStore.appearance.icon_source || "pixel");
}

function applyDockWidthVar() {
  try {
    document.documentElement.style.setProperty("--dock-w", `${dockWidth.value}px`);
  } catch {}
}

function applyDockGeometryVars() {
  applyDockWidthVar();
  try {
    const rect = dockEl.value?.getBoundingClientRect?.();
    if (!rect) return;
    document.documentElement.style.setProperty("--dock-left", `${Math.round(rect.left)}px`);
    document.documentElement.style.setProperty("--dock-right", `${Math.round(rect.right)}px`);
  } catch {}
}

function onItemClick(key) {
  if (key === "avatar") {
    uiStore.closeRight();
    uiStore.toggleLeft("avatar");
    return;
  }
  uiStore.toggleLeft(key);
}

function onResize() {
  applyDockGeometryVars();
}

onMounted(() => {
  applyDockGeometryVars();
  window.addEventListener("resize", onResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
});

watch(dockWidth, () => applyDockGeometryVars());
</script>

<template>
  <nav
    ref="dockEl"
    class="dock panel"
    aria-label="导航"
    :data-expanded="expanded ? '1' : '0'"
    :style="{ width: dockWidth + 'px' }"
  >
    <button
      v-for="it in items"
      :key="it.key"
      class="dock-btn"
      :class="{ active: uiStore.leftSection === it.key && uiStore.leftExpanded }"
      :title="it.label"
      @click="onItemClick(it.key)"
    >
      <span class="dock-ico" v-html="iconHtml('dock', it.ico)"></span>
      <span class="dock-txt">{{ it.label }}</span>
      <span class="rail" aria-hidden="true"></span>
    </button>
  </nav>
</template>

<style scoped>
.dock {
  padding: 8px 6px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 10px;
}

.dock-btn {
  width: 100%;
  height: 40px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.14);
  background: rgba(0, 0, 0, 0.18);
  color: rgba(255, 255, 255, 0.82);
  cursor: pointer;
  display: grid;
  grid-template-columns: 40px 1fr;
  align-items: center;
  position: relative;
  transition: background 160ms ease, border-color 160ms ease, transform 160ms ease;
}

.dock-btn:hover {
  border-color: rgba(255, 255, 255, 0.24);
  background: rgba(0, 0, 0, 0.24);
}

.dock-btn:active {
  transform: translateY(1px);
}

.dock-btn.active {
  border-color: rgba(127, 223, 255, 0.35);
  box-shadow: 0 0 0 1px rgba(127, 223, 255, 0.08), 0 14px 30px rgba(0, 0, 0, 0.35);
}

.rail {
  position: absolute;
  left: 0;
  top: 7px;
  bottom: 7px;
  width: 3px;
  border-radius: 999px;
  background: rgba(127, 223, 255, 0);
  transition: background 160ms ease;
}
.dock-btn.active .rail {
  background: rgba(127, 223, 255, 0.55);
}

.dock-ico {
  width: 18px;
  height: 18px;
  display: inline-flex;
  justify-self: center;
  color: rgba(255, 255, 255, 0.82);
}
.dock-ico :deep(svg) {
  width: 18px;
  height: 18px;
  display: block;
}

.dock-txt {
  color: rgba(255, 255, 255, 0.82);
  font-size: 12px;
  letter-spacing: 0.2px;
  text-align: left;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.dock[data-expanded="0"] .dock-txt {
  display: none;
}
.dock[data-expanded="0"] .dock-btn {
  grid-template-columns: 1fr;
}
.dock[data-expanded="0"] .dock-ico {
  justify-self: center;
}
</style>
