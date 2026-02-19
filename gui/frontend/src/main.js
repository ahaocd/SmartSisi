import { createApp, watch } from "vue";
import { createPinia } from "pinia";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import HomePage from "./pages/HomePage.vue";
import SettingsPage from "./pages/SettingsPage.vue";
import ActivityPage from "./pages/ActivityPage.vue";

import "./styles/global.css";
import { useConfigStore } from "./stores/configStore";
import { useBackendStore } from "./stores/backendStore";
import { useSystemStore } from "./stores/systemStore";
import { useEventStore } from "./stores/eventStore";
import { startWsBridge } from "./api/wsBridge";
import { apiGetAllConfig, apiGetRunStatus, apiGetMsg } from "./api/sisiApi";
import { mapBackendConfigToUiPatch } from "./api/configBridge";

try {
  if (typeof __BUILD_ID__ !== "undefined") {
    console.info("[SmartSisi UI] build:", __BUILD_ID__);
  }
} catch {}

const router = createRouter({
  history: createWebHistory("/"),
  routes: [
    { path: "/", component: HomePage },
    { path: "/settings", component: SettingsPage },
    { path: "/activity", component: ActivityPage }
  ]
});

const app = createApp(App);
const pinia = createPinia();
app.use(pinia).use(router);

const configStore = useConfigStore(pinia);
configStore.load();
const backendStore = useBackendStore(pinia);
const systemStore = useSystemStore(pinia);
const eventStore = useEventStore(pinia);
systemStore.initStorageSync();
systemStore.setActiveAudioSystem(configStore.shared.active_audio_system_id);

let syncingBackendConfig = false;
const HISTORY_USER_KEY = "smartsisi_history_user_id_v1";

function parseBoolLike(v, fallback = false) {
  if (typeof v === "boolean") return v;
  if (typeof v === "number") return v !== 0;
  const s = String(v || "").trim().toLowerCase();
  if (!s) return fallback;
  if (["1", "true", "yes", "on"].includes(s)) return true;
  if (["0", "false", "no", "off"].includes(s)) return false;
  return fallback;
}

function loadHistoryUserId() {
  if (typeof window === "undefined") return "";
  try {
    return String(localStorage.getItem(HISTORY_USER_KEY) || "").trim();
  } catch {
    return "";
  }
}

function persistHistoryUserId(userId) {
  const uid = String(userId || "").trim();
  if (!uid || typeof window === "undefined") return;
  try {
    localStorage.setItem(HISTORY_USER_KEY, uid);
  } catch {}
}

async function syncConfigFromBackend(reason = "startup") {
  if (syncingBackendConfig) return;
  if (configStore.backend.mode !== "real") return;
  syncingBackendConfig = true;
  try {
    const data = await apiGetAllConfig(configStore.backend.http_base);
    const backendConfig = data?.config_json;
    if (!backendConfig || typeof backendConfig !== "object") {
      eventStore.pushEvent({
        system_id: systemStore.currentSystemId,
        kind: "status",
        level: "warning",
        title: "后端配置同步",
        message: `已请求 /api/config/all，但未拿到 config_json（${reason}）`
      });
      return;
    }

    configStore.setBackendSnapshot(data);

    const { sharedPatch } = mapBackendConfigToUiPatch(backendConfig, configStore.config);
    const systemConf = data?.system_conf;
    const halfDuplexRaw = systemConf?.key?.half_duplex_enabled;
    if (halfDuplexRaw != null && String(halfDuplexRaw).trim() !== "") {
      const isHalf = parseBoolLike(halfDuplexRaw, true);
      sharedPatch.duplex_mode = isHalf ? "half" : "full";
      sharedPatch.ptt_enabled = isHalf;
    }
    if (Object.keys(sharedPatch).length) {
      configStore.patchShared(sharedPatch);
    }

    eventStore.pushEvent({
      system_id: systemStore.currentSystemId,
      kind: "status",
      level: "success",
      title: "后端配置同步",
      message: `已从后端拉取并应用 ${Object.keys(sharedPatch).length} 个字段（${reason}）`
    });
  } catch (e) {
    eventStore.pushEvent({
      system_id: systemStore.currentSystemId,
      kind: "status",
      level: "error",
      title: "后端配置同步失败",
      message: String(e?.message || e)
    });
  } finally {
    syncingBackendConfig = false;
  }
}

async function syncRunStateFromBackend(reason = "startup") {
  if (configStore.backend.mode !== "real") return;
  try {
    const st = await apiGetRunStatus(configStore.backend.http_base);
    const running = !!(st && typeof st === "object" && st.status === true);
    backendStore.setLiveState(running ? 1 : 0);
    eventStore.pushEvent({
      system_id: systemStore.currentSystemId,
      kind: "status",
      level: "info",
      title: "运行状态同步",
      message: `后端状态：${running ? "运行中" : "未运行"}（${reason}）`,
      payload: { response: st }
    });
  } catch (e) {
    eventStore.pushEvent({
      system_id: systemStore.currentSystemId,
      kind: "status",
      level: "warning",
      title: "运行状态同步失败",
      message: String(e?.message || e)
    });
  }
}

async function syncHistoryFromBackend(reason = "startup") {
  if (configStore.backend.mode !== "real") return;
  try {
    const payload = { limit: 320 };
    const rememberedUser = loadHistoryUserId();
    if (rememberedUser) payload.canonical_user_id = rememberedUser;
    const data = await apiGetMsg(configStore.backend.http_base, payload);
    if (data && typeof data === "object" && data.user_id) {
      persistHistoryUserId(data.user_id);
    }
    const changed = systemStore.hydrateHistoryFromBackend(data || {});
    if (changed) {
      eventStore.pushEvent({
        system_id: systemStore.currentSystemId,
        kind: "status",
        level: "success",
        title: "历史同步",
        message: `已从后端恢复历史（${reason}）`
      });
    }
  } catch (e) {
    eventStore.pushEvent({
      system_id: systemStore.currentSystemId,
      kind: "status",
      level: "warning",
      title: "历史同步失败",
      message: String(e?.message || e)
    });
  }
}

watch(
  () => `${configStore.backend.mode}|${configStore.backend.http_base}`,
  () => {
    syncConfigFromBackend("backend-changed");
    syncRunStateFromBackend("backend-changed");
    syncHistoryFromBackend("backend-changed");
  },
  { immediate: true }
);

startWsBridge(pinia);

app.mount("#app");
