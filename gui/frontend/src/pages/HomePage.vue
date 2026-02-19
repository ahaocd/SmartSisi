<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watchEffect } from "vue";
import SystemSwitcher from "../components/SystemSwitcher.vue";
import ChatMessageList from "../components/ChatMessageList.vue";
import ChatComposer from "../components/ChatComposer.vue";
import LeftBar from "../components/LeftBar.vue";
import RightDockPanel from "../components/RightDockPanel.vue";
import CharacterPanel from "../components/CharacterPanel.vue";
import Live2DControls from "../components/Live2DControls.vue";
import Live2DLoader from "../components/Live2DLoader.vue";
import Live2DSafeArea from "../components/Live2DSafeArea.vue";
import { useUiStore } from "../stores/uiStore";
import { useMediaQuery } from "../ui/useMediaQuery";
import { computeShellWidths } from "../ui/layout";
import InkFxCanvas from "../components/InkFxCanvas.vue";
import { useConfigStore } from "../stores/configStore";
import { useBackendStore } from "../stores/backendStore";

const uiStore = useUiStore();
const isNarrow = useMediaQuery("(max-width: 980px)");
const isWideDock = useMediaQuery("(min-width: 1100px)");
const configStore = useConfigStore();
const backendStore = useBackendStore();

const RIGHT_PANEL_W = 420;
const WORK_GAP = 14;
const WORK_PAD = 14;
const viewportW = ref(0);

function onResize() {
  try {
    viewportW.value = window.innerWidth || 0;
  } catch {
    viewportW.value = 0;
  }
}

onMounted(() => {
  onResize();
  window.addEventListener("resize", onResize, { passive: true });
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
});

const dockWidth = computed(() => {
  const dockMode = configStore.appearance.dock_mode || "auto";
  const dockExpanded = dockMode === "expand" ? true : dockMode === "collapse" ? false : !!isWideDock.value;
  return dockExpanded ? 150 : 56;
});

const SHELL_MAX_W = 1230;
const layout = computed(() => {
  const shellW = Math.min(viewportW.value || 0, SHELL_MAX_W);
  if (isNarrow.value) {
    return computeShellWidths({
      viewportW: shellW,
      dockW: dockWidth.value,
      leftOpen: false,
      drawerOpen: false,
      pad: WORK_PAD,
      gap: WORK_GAP,
      chatMin: 360,
      leftMax: 520,
      leftMin: 320
    });
  }
  return computeShellWidths({
    viewportW: shellW,
    dockW: dockWidth.value,
    leftOpen: uiStore.leftExpanded,
    leftOverlay: true,
    drawerOpen: uiStore.rightPanelOpen,
    pad: WORK_PAD,
    gap: WORK_GAP,
    chatMin: 360,
    drawerMax: RIGHT_PANEL_W,
    leftMax: 520,
    leftMin: 320
  });
});

const leftbarWidth = computed(() => layout.value.leftbarW);
const drawerTrackWidth = computed(() => layout.value.drawerW);

const live2dVisible = computed(() => true);

watchEffect(() => {
  if (!isNarrow.value && layout.value.forceCloseLeft) uiStore.closeLeft();
  try {
    document.documentElement.dataset.live2d = live2dVisible.value ? "avatar" : "off";
    document.documentElement.classList.toggle("live2d-music", !!backendStore.musicPlaying);
    const drawerForLive2d = uiStore.rightPanelOpen ? RIGHT_PANEL_W : 0;
    document.documentElement.style.setProperty("--drawer-w-root", `${drawerForLive2d}px`);
    document.documentElement.style.setProperty("--leftbar-w-root", `${leftbarWidth.value}px`);
  } catch {}
});
</script>

<template>
  <div class="app-shell">
    <InkFxCanvas />
    <div class="bg-grid"></div>
    <div class="bg-scanline"></div>
    <Live2DLoader />
    <Live2DSafeArea />

    <div class="shell-inner">
      <div class="topbar">
        <div class="top-left">
          <div class="brand">
            <span class="brand-dot"></span>
            <span>SmartSisi</span>
          </div>
          <SystemSwitcher />
        </div>
        <div class="top-actions"></div>
      </div>

      <div
        class="work-grid"
        :style="{
          '--leftbar-w': leftbarWidth + 'px',
          '--drawer-w': drawerTrackWidth + 'px',
          '--leftsheet-w': (isNarrow ? 360 : layout.leftW) + 'px'
        }"
      >
        <LeftBar />
        <div class="main-rail">
          <ChatMessageList />
          <ChatComposer />
        </div>
        <RightDockPanel :width="RIGHT_PANEL_W">
          <div v-if="uiStore.rightSection === 'avatar'" style="display: flex; flex-direction: column; gap: 12px; padding: 12px">
            <CharacterPanel />
            <Live2DControls />
          </div>
        </RightDockPanel>
      </div>
    </div>
  </div>
</template>

<style scoped>
.app-shell {
  position: relative;
}

.shell-inner {
  position: relative;
  z-index: 2;
}
</style>
