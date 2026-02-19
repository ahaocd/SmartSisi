<script setup>
import { darkTheme, NConfigProvider, NNotificationProvider, NMessageProvider } from "naive-ui";
import { useThemeOverrides } from "./theme/useThemeOverrides";
import { onBeforeUnmount, onMounted, watch } from "vue";
import { useConfigStore } from "./stores/configStore";
import { idbGet } from "./ui/idb";

const themeOverrides = useThemeOverrides();
const configStore = useConfigStore();

let bgUrl = null;
let lastRev = 0;
let lastBgLogAt = 0;

async function reloadBackgroundFromIdb() {
  const blob = await idbGet("background_image");
  try {
    if (bgUrl) URL.revokeObjectURL(bgUrl);
  } catch {}
  bgUrl = null;
  if (blob instanceof Blob) {
    bgUrl = URL.createObjectURL(blob);
  }
}

const DOPAMINE_PALETTES = [
  { name: "hermes", primary: "#F36F21", secondary: "#2E241E", tertiary: "#F5EBDD", accent2: "#58C4D8" },
  { name: "tiffany", primary: "#81D8D0", secondary: "#1F2A30", tertiary: "#DDE3E7", accent2: "#A7D9FF" },
  { name: "cartier", primary: "#7A1F2E", secondary: "#C8A24D", tertiary: "#F2E8DD", accent2: "#E49B66" },
  { name: "chanel", primary: "#0B0B0B", secondary: "#C5A46D", tertiary: "#F4F1EC", accent2: "#9DB6C8" },
  { name: "bottega", primary: "#4DAA57", secondary: "#1F3D2F", tertiary: "#D8CBB9", accent2: "#9BD58D" },
  { name: "dior", primary: "#13254A", secondary: "#C89A95", tertiary: "#EDE9E2", accent2: "#8BB5FF" },
  { name: "gucci", primary: "#0F4A3A", secondary: "#8D1A20", tertiary: "#B88D5A", accent2: "#F0C084" },
  { name: "loewe", primary: "#C96E48", secondary: "#8A4B37", tertiary: "#E9D8C3", accent2: "#F2A56B" }
];

function clamp01(v) {
  return Math.max(0, Math.min(1, Number(v) || 0));
}

function mulberry32(seed) {
  let t = (Number(seed) || 202) >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let x = Math.imul(t ^ (t >>> 15), 1 | t);
    x ^= x + Math.imul(x ^ (x >>> 7), 61 | x);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

function hexToRgb(hex) {
  const h = String(hex || "").replace("#", "").trim();
  if (h.length !== 6) return { r: 255, g: 255, b: 255 };
  const n = Number.parseInt(h, 16);
  if (!Number.isFinite(n)) return { r: 255, g: 255, b: 255 };
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

function rgbToHex(r, g, b) {
  const to2 = (n) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, "0");
  return `#${to2(r)}${to2(g)}${to2(b)}`;
}

function tintHex(hex, ratio) {
  const c = hexToRgb(hex);
  const p = clamp01(ratio);
  return rgbToHex(c.r + (255 - c.r) * p, c.g + (255 - c.g) * p, c.b + (255 - c.b) * p);
}

function shadeHex(hex, ratio) {
  const c = hexToRgb(hex);
  const p = clamp01(ratio);
  return rgbToHex(c.r * (1 - p), c.g * (1 - p), c.b * (1 - p));
}

function rgba(hex, alpha) {
  const c = hexToRgb(hex);
  const a = Math.max(0, Math.min(1, Number(alpha) || 0));
  return `rgba(${c.r}, ${c.g}, ${c.b}, ${a.toFixed(3)})`;
}

function pickDopaminePalette(seed, variant = 0) {
  const rnd = mulberry32(seed);
  const len = DOPAMINE_PALETTES.length;
  const base = Math.floor(rnd() * len);
  const shift = Math.max(0, Math.floor(Number(variant) || 0));
  const idx = (base + shift) % len;
  return DOPAMINE_PALETTES[idx] || DOPAMINE_PALETTES[0];
}

function applyBgVars() {
  const a = configStore.appearance;
  const dim = Number(a.background_dim ?? 0.35);
  const blur = Number(a.background_blur ?? 10);
  const colorwayMode = String(a.colorway_mode || "default");
  const colorwaySeed = Math.max(1, Math.floor(Number(a.colorway_seed) || 202));
  const colorwayVariant = Math.max(0, Math.floor(Number(a.colorway_variant) || 0));
  const dimNorm = Math.max(0, Math.min(1, dim / 0.8));
  document.documentElement.style.setProperty("--user-bg-dim", String(dim));
  document.documentElement.style.setProperty("--user-bg-blur", String(blur));
  let chatWindowAlpha = Math.max(0.04, Math.min(0.46, 0.04 + dimNorm * 0.42));
  let chatWindowBorderAlpha = Math.max(0.12, Math.min(0.6, 0.12 + dimNorm * 0.48));
  let sideWindowAlpha = Math.max(0.02, Math.min(0.3, 0.02 + dimNorm * 0.28));
  let sideWindowBorderAlpha = Math.max(0.06, Math.min(0.4, 0.06 + dimNorm * 0.34));
  const sideWindowBlur = Math.max(0, blur * 0.9);
  let themePrimary = "#f7a8c6";
  let themePrimaryHover = "#f9bdd6";
  let themePrimaryPressed = "#ef8eb6";
  let themeAccent2 = "#7fdfff";
  let sliderAccent = "rgba(127, 223, 255, 0.85)";
  let uiRowBg = "rgba(0, 0, 0, 0.16)";
  let uiRowBorder = "rgba(255, 255, 255, 0.10)";
  let uiHdrBg = "rgba(12, 14, 22, 0.88)";
  let uiTagBg = "rgba(247, 168, 198, 0.10)";
  let uiTagBorder = "rgba(255, 255, 255, 0.14)";
  let uiTagStrongBorder = "rgba(247, 168, 198, 0.22)";
  let uiTagStrongColor = "rgba(247, 168, 198, 0.95)";
  let bgOverlay = `rgba(9, 9, 11, ${dim.toFixed(3)})`;
  let dopamineIntensity = 0;
  let dopamineC1 = "rgba(243, 111, 33, 0.22)";
  let dopamineC2 = "rgba(129, 216, 208, 0.18)";
  let dopamineC3 = "rgba(122, 31, 46, 0.2)";
  let dopamineSpeed = "16s";

  if (colorwayMode === "dopamine202") {
    const palette = pickDopaminePalette(colorwaySeed, colorwayVariant);
    const paletteIntensity = 0.56;
    const paletteSpeed = 0.52;
    themePrimary = palette.primary;
    themePrimaryHover = tintHex(themePrimary, 0.2);
    themePrimaryPressed = shadeHex(themePrimary, 0.16);
    themeAccent2 = palette.accent2;
    sliderAccent = rgba(themeAccent2, 0.9);
    uiRowBg = rgba(palette.secondary, 0.14 + paletteIntensity * 0.18);
    uiRowBorder = rgba(themeAccent2, 0.16 + paletteIntensity * 0.28);
    uiHdrBg = `linear-gradient(110deg, ${rgba(palette.secondary, 0.88)} 0%, ${rgba(themePrimary, 0.34)} 56%, ${rgba(palette.tertiary, 0.22)} 100%)`;
    uiTagBg = rgba(themePrimary, 0.14 + paletteIntensity * 0.2);
    uiTagBorder = rgba(themeAccent2, 0.18 + paletteIntensity * 0.3);
    uiTagStrongBorder = rgba(palette.tertiary, 0.3 + paletteIntensity * 0.36);
    uiTagStrongColor = rgba(palette.tertiary, 0.84);
    bgOverlay = `linear-gradient(130deg, ${rgba(themePrimary, 0.2 + paletteIntensity * 0.26)} 0%, ${rgba(palette.secondary, 0.2 + paletteIntensity * 0.2)} 48%, ${rgba(themeAccent2, 0.18 + paletteIntensity * 0.22)} 100%)`;
    dopamineIntensity = 0.2 + paletteIntensity * 0.56;
    dopamineC1 = rgba(themePrimary, 0.26 + paletteIntensity * 0.38);
    dopamineC2 = rgba(themeAccent2, 0.24 + paletteIntensity * 0.34);
    dopamineC3 = rgba(palette.tertiary, 0.2 + paletteIntensity * 0.26);
    dopamineSpeed = `${(22 - paletteSpeed * 14).toFixed(1)}s`;
    chatWindowAlpha = Math.min(0.52, chatWindowAlpha + paletteIntensity * 0.08);
    chatWindowBorderAlpha = Math.min(0.66, chatWindowBorderAlpha + paletteIntensity * 0.1);
    sideWindowAlpha = Math.min(0.36, sideWindowAlpha + paletteIntensity * 0.06);
    sideWindowBorderAlpha = Math.min(0.48, sideWindowBorderAlpha + paletteIntensity * 0.08);
  }

  document.documentElement.style.setProperty("--chat-window-alpha", String(chatWindowAlpha));
  document.documentElement.style.setProperty("--chat-window-border-alpha", String(chatWindowBorderAlpha));
  document.documentElement.style.setProperty("--chat-window-blur", String(blur));
  document.documentElement.style.setProperty("--side-window-alpha", String(sideWindowAlpha));
  document.documentElement.style.setProperty("--side-window-border-alpha", String(sideWindowBorderAlpha));
  document.documentElement.style.setProperty("--side-window-blur", String(sideWindowBlur));
  document.documentElement.style.setProperty("--theme-primary", themePrimary);
  document.documentElement.style.setProperty("--theme-primary-hover", themePrimaryHover);
  document.documentElement.style.setProperty("--theme-primary-pressed", themePrimaryPressed);
  document.documentElement.style.setProperty("--theme-accent-2", themeAccent2);
  document.documentElement.style.setProperty("--slider-accent", sliderAccent);
  document.documentElement.style.setProperty("--ui-row-bg", uiRowBg);
  document.documentElement.style.setProperty("--ui-row-border", uiRowBorder);
  document.documentElement.style.setProperty("--ui-hdr-bg", uiHdrBg);
  document.documentElement.style.setProperty("--ui-tag-bg", uiTagBg);
  document.documentElement.style.setProperty("--ui-tag-border", uiTagBorder);
  document.documentElement.style.setProperty("--ui-tag-strong-border", uiTagStrongBorder);
  document.documentElement.style.setProperty("--ui-tag-strong-color", uiTagStrongColor);
  document.documentElement.style.setProperty("--bg-overlay", bgOverlay);
  document.documentElement.style.setProperty("--dopamine-intensity", String(dopamineIntensity));
  document.documentElement.style.setProperty("--dopamine-c1", dopamineC1);
  document.documentElement.style.setProperty("--dopamine-c2", dopamineC2);
  document.documentElement.style.setProperty("--dopamine-c3", dopamineC3);
  document.documentElement.style.setProperty("--dopamine-speed", dopamineSpeed);
  if (!a.background_enabled || !bgUrl) document.documentElement.style.setProperty("--user-bg", "none");
  else document.documentElement.style.setProperty("--user-bg", `url("${bgUrl}")`);
  const now = Date.now();
  if (now - lastBgLogAt >= 120) {
    lastBgLogAt = now;
    try {
      console.info("[BG][vars]", {
        enabled: !!a.background_enabled,
        hasImage: !!bgUrl,
        colorwayMode,
        colorwaySeed,
        colorwayVariant,
        dim,
        blur,
        chatWindowAlpha,
        chatWindowBorderAlpha,
        sideWindowAlpha,
        sideWindowBorderAlpha,
        sideWindowBlur
      });
    } catch {}
  }
}

onMounted(async () => {
  configStore.load();
  lastRev = Number(configStore.appearance.background_rev || 0);
  await reloadBackgroundFromIdb();
  applyBgVars();
});

watch(
  () => configStore.appearance,
  async () => {
    const rev = Number(configStore.appearance.background_rev || 0);
    if (rev !== lastRev) {
      lastRev = rev;
      await reloadBackgroundFromIdb();
    }
    applyBgVars();
  },
  { deep: true }
);

onBeforeUnmount(() => {
  try {
    if (bgUrl) URL.revokeObjectURL(bgUrl);
  } catch {}
  bgUrl = null;
});
</script>

<template>
  <n-config-provider :theme="darkTheme" :theme-overrides="themeOverrides">
    <n-notification-provider :max="6" placement="top-right">
      <n-message-provider :max="4">
        <div class="bg-photo"></div>
        <router-view />
      </n-message-provider>
    </n-notification-provider>
  </n-config-provider>
</template>
