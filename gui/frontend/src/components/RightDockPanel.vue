<script setup>
import { computed } from "vue";
import { useUiStore } from "../stores/uiStore";

const props = defineProps({
  width: { type: Number, default: 390 }
});

const uiStore = useUiStore();
const open = computed(() => uiStore.rightPanelOpen);
</script>

<template>
  <div v-if="open" class="mask" @click="uiStore.closeRight"></div>
  <div class="rightdock" :data-open="open ? '1' : '0'" :style="{ width: open ? width + 'px' : '0px' }">
    <div class="rightdock-inner panel" :style="{ width: width + 'px' }">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.mask {
  display: none;
}

.rightdock {
  min-width: 0;
  height: 100%;
  overflow: hidden;
  display: flex;
  justify-content: flex-end;
  transition: width 260ms cubic-bezier(0.22, 0.61, 0.36, 1);
  will-change: width;
}

.rightdock-inner {
  height: 100%;
  overflow: auto;
  transform: none;
  opacity: 0;
  transition: opacity 220ms ease;
  will-change: opacity;
}

.rightdock-inner::-webkit-scrollbar {
  width: 12px;
  height: 12px;
}

.rightdock[data-open="1"] .rightdock-inner {
  opacity: 1;
}

@media (prefers-reduced-motion: reduce) {
  .rightdock,
  .rightdock-inner {
    transition: none !important;
  }
}

/* On narrow screens, behave like a drawer overlay. */
@media (max-width: 980px) {
  .mask {
    display: block;
    position: fixed;
    top: var(--topbar-h);
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.42);
    backdrop-filter: blur(2px);
    z-index: 55;
  }

  .rightdock {
    position: fixed;
    top: var(--topbar-h);
    right: 0;
    bottom: 0;
    height: auto;
    z-index: 60;
    box-shadow: 0 24px 60px rgba(0, 0, 0, 0.55);
  }

  .rightdock-inner {
    height: 100%;
  }
}
</style>
