<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { NScrollbar } from "naive-ui";
import { useSystemStore } from "../stores/systemStore";
import FlowChips from "./FlowChips.vue";

const systemStore = useSystemStore();
const viewport = ref(null);
const messages = computed(() => systemStore.currentMessages);
const isEmpty = computed(() => (messages.value || []).length === 0);
const openStreamMessageId = computed(() => systemStore.openStreamMessageIdBySystem?.[systemStore.currentSystemId] || null);
const pinnedToBottom = ref(true);
const BOTTOM_GAP = 90;
let scrollEl = null;
let followRaf = 0;

function isImageAttachment(att) {
  const kind = String(att?.kind || "").toLowerCase();
  const mime = String(att?.mime || "").toLowerCase();
  return kind === "image" || mime.startsWith("image/");
}

function isVideoAttachment(att) {
  const kind = String(att?.kind || "").toLowerCase();
  const mime = String(att?.mime || "").toLowerCase();
  return kind === "video" || mime.startsWith("video/");
}

function formatSize(size) {
  const n = Number(size || 0);
  if (!Number.isFinite(n) || n <= 0) return "";
  if (n < 1024) return `${n}B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)}KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)}MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(1)}GB`;
}

function getScrollEl() {
  const inst = viewport.value;
  if (inst) {
    try {
      const c = inst.containerRef?.value ?? inst.containerRef;
      if (c) return c;
    } catch {}
    try {
      const el = inst.$el;
      if (el?.querySelector) {
        const c = el.querySelector(".n-scrollbar-container");
        if (c) return c;
      }
    } catch {}
  }
  try {
    const c = document.querySelector(".panel.chat .n-scrollbar-container");
    if (c) return c;
  } catch {}
  return null;
}

function ensureScrollEl() {
  const el = getScrollEl();
  if (!el) return null;
  if (scrollEl && scrollEl !== el) {
    try {
      scrollEl.removeEventListener("scroll", updatePinned);
    } catch {}
  }
  if (scrollEl !== el) {
    scrollEl = el;
    try {
      scrollEl.addEventListener("scroll", updatePinned, { passive: true });
    } catch {}
  }
  return scrollEl;
}

async function scrollToBottom(behavior = "auto") {
  await nextTick();
  const el = ensureScrollEl();
  if (!el) {
    pinnedToBottom.value = true;
    return;
  }
  const target = Math.max(0, el.scrollHeight - el.clientHeight);
  el.scrollTo({ top: target, behavior });
}

const tailSignature = computed(() => {
  const list = messages.value || [];
  const last = list[list.length - 1] || null;
  const lastId = String(last?.id || "");
  const lastContent = String(last?.content || "");
  const pending = last?.meta?.pending_reply ? "1" : "0";
  const streamOpen = last?.meta?.stream_open ? "1" : "0";
  const attCount = Array.isArray(last?.attachments) ? String(last.attachments.length) : "0";
  return [
    String(systemStore.currentSystemId || ""),
    String(openStreamMessageId.value || ""),
    String(list.length),
    lastId,
    lastContent,
    pending,
    streamOpen,
    attCount
  ].join("|");
});

watch(
  () => messages.value.length,
  () => {
    updatePinned();
    if (pinnedToBottom.value) scrollToBottom("auto");
  }
);

watch(
  () => messages.value[messages.value.length - 1]?.content,
  () => {
    updatePinned();
    if (!pinnedToBottom.value) return;
    if (followRaf) cancelAnimationFrame(followRaf);
    followRaf = requestAnimationFrame(() => {
      scrollToBottom("smooth");
    });
  }
);

watch(
  () => systemStore.currentSystemId,
  () => {
    pinnedToBottom.value = true;
    scrollToBottom("auto");
    updatePinned();
  }
);

watch(tailSignature, () => {
  updatePinned();
  if (!pinnedToBottom.value) return;
  if (followRaf) cancelAnimationFrame(followRaf);
  followRaf = requestAnimationFrame(() => {
    scrollToBottom("smooth");
  });
});

function updatePinned() {
  const el = ensureScrollEl();
  if (!el) {
    pinnedToBottom.value = true;
    return;
  }
  const remain = el.scrollHeight - el.scrollTop - el.clientHeight;
  const threshold = BOTTOM_GAP + 2;
  pinnedToBottom.value = remain <= threshold;
}

onMounted(() => {
  let tries = 0;
  const tick = () => {
    const el = ensureScrollEl();
    if (el) {
      scrollToBottom("auto");
      updatePinned();
      return;
    }
    if (tries < 20) {
      tries += 1;
      setTimeout(tick, 50);
    }
  };
  tick();
});

onBeforeUnmount(() => {
  try {
    if (scrollEl) scrollEl.removeEventListener("scroll", updatePinned);
  } catch {}
  scrollEl = null;
  if (followRaf) cancelAnimationFrame(followRaf);
  followRaf = 0;
});
</script>

<template>
  <div class="panel chat" :data-empty="isEmpty ? '1' : '0'">
    <n-scrollbar ref="viewport" trigger="none" :size="6" style="height: 100%">
      <div class="chat-inner" :data-empty="isEmpty ? '1' : '0'">
        <div v-for="m in messages" :key="m.id" class="row" :data-role="m.role">
          <div class="bubble">
            <div v-if="m.role === 'assistant' && !String(m.content || '').trim() && m.meta?.pending_reply" class="typing">...</div>
            <div v-else class="content">{{ m.content }}</div>
            <div v-if="Array.isArray(m.attachments) && m.attachments.length" class="attachments">
              <div
                v-for="att in m.attachments"
                :key="att.id || att.preview_url"
                class="att-card"
                :data-kind="isImageAttachment(att) ? 'image' : isVideoAttachment(att) ? 'video' : 'file'"
              >
                <a
                  v-if="isImageAttachment(att)"
                  class="att-preview-link"
                  :href="att.download_url || att.preview_url"
                  target="_blank"
                  rel="noopener"
                  :title="att.name || 'image'"
                >
                  <img class="att-image" :src="att.preview_url" :alt="att.name || 'image'" loading="lazy" />
                </a>
                <video
                  v-else-if="isVideoAttachment(att)"
                  class="att-video"
                  :src="att.preview_url"
                  controls
                  preload="metadata"
                ></video>
                <div v-else class="att-file">附件: {{ att.name || "附件" }}</div>
                <div v-if="!isImageAttachment(att) && !isVideoAttachment(att)" class="att-meta">
                  <span class="att-name">{{ att.name || "附件" }}</span>
                  <span class="att-size">{{ formatSize(att.size) }}</span>
                  <a class="att-link" :href="att.download_url || att.preview_url" target="_blank" rel="noopener">下载</a>
                </div>
              </div>
            </div>
          </div>
          <FlowChips
            v-if="m.role === 'assistant'"
            class="flow-inline"
            :trace-id="m.meta?.trace_id"
            :message-id="m.id"
            :placeholder="
              !!(
                m.meta?.pending_reply ||
                m.meta?.stream_open ||
                (openStreamMessageId && m.id === openStreamMessageId)
              )
            "
            variant="bars"
          />
        </div>
      </div>
    </n-scrollbar>
  </div>
</template>

<style scoped>
.chat {
  flex: 1 1 auto;
  min-height: 0;
  overflow: visible;
  position: relative;
  width: 100%;
  max-width: var(--chat-max-w);
  margin: 0;
  background:
    linear-gradient(180deg, rgba(8, 10, 16, 0.56), rgba(8, 10, 16, 0.56)),
    rgba(255, 255, 255, calc(var(--chat-window-alpha, 0.06) * 0.58));
  border-color: rgba(255, 255, 255, calc(var(--chat-window-border-alpha, 0.2) * 0.82));
  backdrop-filter: blur(calc(var(--chat-window-blur, 8) * 1px)) saturate(1.2);
}
.chat[data-empty="1"] {
  height: auto;
  align-self: start;
}
.chat-inner {
  padding: 12px 12px 90px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.chat-inner[data-empty="1"] {
  justify-content: center;
}
.row {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.row[data-role="user"] {
  align-items: flex-end;
}
.row[data-role="assistant"] {
  align-items: flex-start;
}
.bubble {
  max-width: 80%;
  padding: 6px 12px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, calc(var(--chat-window-border-alpha, 0.2) * 0.58));
  background:
    linear-gradient(180deg, rgba(11, 13, 20, 0.64), rgba(11, 13, 20, 0.64)),
    rgba(255, 255, 255, calc(var(--chat-window-alpha, 0.06) * 0.5));
  min-width: 0;
  overflow: hidden;
}

.row[data-role="assistant"] .bubble {
  background:
    linear-gradient(180deg, rgba(10, 12, 18, 0.66), rgba(10, 12, 18, 0.66)),
    rgba(255, 255, 255, calc(var(--chat-window-alpha, 0.06) * 0.48));
}

.row[data-role="user"] .bubble {
  background:
    linear-gradient(180deg, rgba(13, 16, 24, 0.7), rgba(13, 16, 24, 0.7)),
    rgba(255, 255, 255, calc(var(--chat-window-alpha, 0.06) * 0.52));
}
.content {
  white-space: normal;
  line-height: 1.55;
  font-size: 13px;
  color: var(--text-0);
  overflow-wrap: break-word;
  word-break: break-word;
}

.attachments {
  margin-top: 8px;
  display: grid;
  gap: 8px;
}

.att-card {
  border: 1px solid rgba(255, 255, 255, 0.12);
  border-radius: 10px;
  padding: 4px;
  background: rgba(0, 0, 0, 0.16);
}

.att-preview-link {
  display: block;
  text-decoration: none;
}

.att-image,
.att-video {
  display: block;
  width: min(420px, 100%);
  max-height: 280px;
  border-radius: 8px;
  object-fit: cover;
  background: rgba(0, 0, 0, 0.28);
}

.att-card[data-kind="image"] .att-image {
  cursor: zoom-in;
}

.att-file {
  font-size: 12px;
  color: var(--text-1);
}

.att-meta {
  margin-top: 6px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.att-name {
  font-size: 12px;
  color: var(--text-0);
}

.att-size {
  font-size: 11px;
  color: var(--text-2);
}

.att-link {
  font-size: 11px;
  color: #8fd7ff;
  text-decoration: none;
}

.att-link:hover {
  text-decoration: underline;
}

.flow-inline {
  margin-top: -2px;
  align-self: flex-start;
  max-width: 80%;
}

.typing {
  font-size: 16px;
  line-height: 1;
  letter-spacing: 3px;
  color: rgba(255, 255, 255, 0.55);
}

:deep(.n-scrollbar-rail--vertical) {
  width: 6px;
  right: clamp(10px, var(--live2d-safe-right), 260px);
}

:deep(.n-scrollbar-rail--vertical .n-scrollbar-rail__scrollbar) {
  width: 6px;
  min-width: 6px;
  background: rgba(255, 255, 255, 0.9);
  border-radius: 999px;
}

@media (max-width: 640px) {
  .chat-inner {
    padding: 10px 8px 90px;
    gap: 8px;
  }

  .bubble {
    max-width: 92%;
    padding: 8px 9px;
  }

  .content {
    font-size: 12px;
    line-height: 1.45;
  }
}
</style>
