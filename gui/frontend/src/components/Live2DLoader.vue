<script setup>
import { onMounted } from "vue";

function injectLive2D() {
  const src = `${import.meta.env.BASE_URL}live2d/autoload.js`;
  const existing = document.querySelector(`script[data-live2d="1"]`);
  if (existing) return;
  const s = document.createElement("script");
  s.src = src;
  s.async = true;
  s.dataset.live2d = "1";
  s.onerror = () => {};
  document.head.appendChild(s);
}

onMounted(() => {
  injectLive2D();
});
</script>

<template>
  <span style="display: none" aria-hidden="true"></span>
</template>

