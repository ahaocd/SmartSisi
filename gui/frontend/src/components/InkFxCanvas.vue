<script setup>
/**
 * InkFxCanvas — fullscreen canvas overlay that spawns ink-splash blobs
 * on mouse click / keyboard press, then fades them out.
 * Reads config from configStore.appearance.inkfx_*
 */
import { onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useConfigStore } from "../stores/configStore";

const configStore = useConfigStore();
const canvasRef = ref(null);

let ctx = null;
let raf = null;
let blobs = [];
const HOTKEYS = new Set(["r", "t", "e", "y", "R", "T", "E", "Y"]);

// Ink palette: dark ink tones + accent colors from the theme
const INK_COLORS = [
  "rgba(20, 18, 30, 0.24)",
  "rgba(40, 35, 55, 0.19)",
  "rgba(60, 50, 70, 0.16)",
  "rgba(255, 176, 122, 0.14)",
  "rgba(127, 223, 255, 0.12)",
  "rgba(255, 210, 140, 0.11)",
  "rgba(80, 60, 90, 0.15)"
];

function randomColor() {
  return INK_COLORS[Math.floor(Math.random() * INK_COLORS.length)];
}

function spawnBlob(x, y) {
  const a = configStore.appearance;
  if (!a.inkfx_enabled) return;
  const intensity = Math.max(0.2, Number(a.inkfx_intensity) || 1.2);
  const baseR = 30 + Math.random() * 80;
  // Keep footprint stable and let intensity primarily drive color vividness.
  const r = baseR * (0.92 + Math.min(1, intensity) * 0.18);

  // Spawn denser sub-blobs for richer ink texture.
  const count = 3 + Math.floor(Math.random() * 3);
  const extra = intensity > 1.25 ? 1 : 0;
  for (let i = 0; i < count; i++) {
    const ox = x + (Math.random() - 0.5) * r * 1.2;
    const oy = y + (Math.random() - 0.5) * r * 0.8;
    const sr = r * (0.3 + Math.random() * 0.7);
    const opacityBase = Math.min(0.98, 0.74 + Math.random() * 0.22 + Math.max(0, intensity - 1) * 0.08);
    blobs.push({
      x: ox, y: oy,
      r: sr,
      opacity: opacityBase,
      color: randomColor(),
      rotation: Math.random() * Math.PI * 2,
      scaleX: 0.7 + Math.random() * 0.6,
      scaleY: 0.7 + Math.random() * 0.6,
      decay: (0.0026 + Math.random() * 0.0048) / (1 + Math.max(0, intensity - 1) * 0.35)
    });
  }
  for (let j = 0; j < extra; j++) {
    const ex = x + (Math.random() - 0.5) * r * 0.8;
    const ey = y + (Math.random() - 0.5) * r * 0.6;
    blobs.push({
      x: ex,
      y: ey,
      r: r * (0.26 + Math.random() * 0.22),
      opacity: Math.min(0.98, 0.7 + Math.random() * 0.18),
      color: randomColor(),
      rotation: Math.random() * Math.PI * 2,
      scaleX: 0.75 + Math.random() * 0.45,
      scaleY: 0.75 + Math.random() * 0.45,
      decay: 0.0024 + Math.random() * 0.0036
    });
  }
}

function spawnRandom() {
  if (!canvasRef.value) return;
  const w = canvasRef.value.width;
  const h = canvasRef.value.height;
  spawnBlob(Math.random() * w, Math.random() * h);
}

function onMouseDown(e) {
  if (!configStore.appearance.inkfx_enabled) return;
  spawnRandom();
}

function onKeyDown(e) {
  if (!configStore.appearance.inkfx_enabled) return;
  const mode = configStore.appearance.inkfx_keyboard_mode || "all";
  if (mode === "none") return;
  if (mode === "hotkeys" && !HOTKEYS.has(e.key)) return;
  spawnRandom();
}

function resize() {
  const c = canvasRef.value;
  if (!c) return;
  const dpr = window.devicePixelRatio || 1;
  c.width = window.innerWidth * dpr;
  c.height = window.innerHeight * dpr;
  c.style.width = window.innerWidth + "px";
  c.style.height = window.innerHeight + "px";
  if (ctx) ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function drawBlob(b) {
  if (!ctx) return;
  ctx.save();
  ctx.globalAlpha = b.opacity;
  ctx.translate(b.x, b.y);
  ctx.rotate(b.rotation);
  ctx.scale(b.scaleX, b.scaleY);

  // Organic ink blob shape using bezier curves
  ctx.beginPath();
  const r = b.r;
  const pts = 6;
  for (let i = 0; i <= pts; i++) {
    const angle = (i / pts) * Math.PI * 2;
    const wobble = r * (0.8 + Math.random() * 0.05); // slight jitter for organic feel
    const px = Math.cos(angle) * wobble;
    const py = Math.sin(angle) * wobble;
    if (i === 0) {
      ctx.moveTo(px, py);
    } else {
      const prevAngle = ((i - 0.5) / pts) * Math.PI * 2;
      const cpx = Math.cos(prevAngle) * r * 1.1;
      const cpy = Math.sin(prevAngle) * r * 1.1;
      ctx.quadraticCurveTo(cpx, cpy, px, py);
    }
  }
  ctx.closePath();
  ctx.fillStyle = b.color;
  ctx.fill();
  ctx.restore();
}

function tick() {
  if (!ctx || !canvasRef.value) return;
  const w = canvasRef.value.width / (window.devicePixelRatio || 1);
  const h = canvasRef.value.height / (window.devicePixelRatio || 1);
  ctx.clearRect(0, 0, w, h);

  const blend = configStore.appearance.inkfx_blend || "multiply";
  ctx.globalCompositeOperation = blend;

  for (let i = blobs.length - 1; i >= 0; i--) {
    const b = blobs[i];
    b.opacity -= b.decay;
    if (b.opacity <= 0) {
      blobs.splice(i, 1);
      continue;
    }
    drawBlob(b);
  }

  ctx.globalCompositeOperation = "source-over";
  raf = requestAnimationFrame(tick);
}

onMounted(() => {
  const c = canvasRef.value;
  if (!c) return;
  ctx = c.getContext("2d");
  resize();
  window.addEventListener("resize", resize, { passive: true });
  window.addEventListener("mousedown", onMouseDown, { passive: true });
  window.addEventListener("keydown", onKeyDown);
  raf = requestAnimationFrame(tick);
});

onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf);
  window.removeEventListener("resize", resize);
  window.removeEventListener("mousedown", onMouseDown);
  window.removeEventListener("keydown", onKeyDown);
  ctx = null;
  blobs = [];
});
</script>

<template>
  <canvas
    ref="canvasRef"
    class="inkfx-canvas"
    :style="{ display: configStore.appearance.inkfx_enabled ? 'block' : 'none' }"
  />
</template>

<style scoped>
.inkfx-canvas {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: -1;
}
</style>
