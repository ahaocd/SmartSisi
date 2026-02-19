<script setup>
defineProps({
  title: { type: String, default: "" },
  desc: { type: String, default: "" }
});
</script>

<template>
  <div class="row">
    <div class="meta">
      <div class="title">{{ title }}</div>
      <div v-if="desc" class="desc">{{ desc }}</div>
    </div>
    <div class="ctrl">
      <slot />
    </div>
  </div>
</template>

<style scoped>
.row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 10px;
  border: 1px solid var(--ui-row-border);
  background: var(--ui-row-bg);
  border-radius: 12px;
  flex-wrap: wrap;
}

.meta {
  min-width: 0;
}

.title {
  font-weight: 800;
  letter-spacing: 0.2px;
  line-height: 1.1;
}

.desc {
  margin-top: 4px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.60);
  line-height: 1.3;
}

.ctrl {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 520px) {
  .row {
    flex-direction: column;
    align-items: stretch;
  }

  .ctrl {
    width: 100%;
    justify-content: flex-start;
  }

  .ctrl :deep(.px-input),
  .ctrl :deep(.px-select),
  .ctrl :deep(.px-textarea) {
    width: min(520px, 100%);
  }
}
</style>
