<script setup>
import { computed } from "vue";
import IconDock from "./IconDock.vue";
import LeftDrawer from "./LeftDrawer.vue";
import { useUiStore } from "../stores/uiStore";

const uiStore = useUiStore();

const overlayMode = computed(() => true);
const expanded = computed(() => !!uiStore.leftExpanded);

function onMask() {
  uiStore.closeLeft();
}
</script>

<template>
  <aside class="leftbar" :data-expanded="expanded ? '1' : '0'" :data-overlay="overlayMode ? '1' : '0'">
    <div class="dock-rail">
      <IconDock />
    </div>

    <div v-if="overlayMode && expanded" class="mask" @click="onMask"></div>

    <div class="settings-rail" :class="{ open: expanded, overlay: overlayMode }">
      <LeftDrawer />
    </div>
  </aside>
</template>

<style scoped>
.leftbar {
  min-width: 0;
  height: 100%;
  display: flex;
  gap: var(--work-gap);
  align-items: stretch;
  overflow: hidden;
}

.dock-rail {
  flex: 0 0 auto;
  width: var(--dock-w);
}

.settings-rail {
  flex: 0 0 auto;
  width: var(--leftsheet-w);
  min-width: 0;
  opacity: 0;
  transform: translateX(-10px);
  pointer-events: none;
  transition: transform 200ms ease, opacity 180ms ease;
}

.settings-rail.open {
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}

/* Narrow screens: overlay settings rail, keep Dock clickable. */
.settings-rail.overlay {
  position: fixed;
  top: var(--topbar-h);
  left: calc(var(--dock-right) + var(--work-gap) + var(--leftsheet-offset));
  bottom: 0;
  height: auto;
  width: var(--leftsheet-w);
  max-width: min(
    var(--leftsheet-w),
    calc(100vw - var(--dock-right) - var(--work-gap) - var(--work-pad) - var(--leftsheet-offset))
  );
  z-index: 70;
  padding: 0;
}

.mask {
  position: fixed;
  top: var(--topbar-h);
  left: var(--dock-right);
  right: 0;
  bottom: 0;
  background: transparent;
  backdrop-filter: none;
  pointer-events: auto;
  z-index: 65;
}

@media (prefers-reduced-motion: reduce) {
  .settings-rail {
    transition: none !important;
  }
}
</style>
