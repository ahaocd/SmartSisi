<script setup>
import { computed } from "vue";
import { useRouter } from "vue-router";
import SettingRow from "../components/SettingRow.vue";
import { useConfigStore } from "../stores/configStore";
import { useBackendStore } from "../stores/backendStore";
import { useSystemStore } from "../stores/systemStore";
import { apiSubmit } from "../api/sisiApi";
import { buildBackendPatchFromUiConfig } from "../api/configBridge";

const router = useRouter();
const configStore = useConfigStore();
const backendStore = useBackendStore();
const systemStore = useSystemStore();

const systemName = computed(() => systemStore.currentSystem?.name || systemStore.currentSystemId);
const currentModel = computed(() => configStore.systemConfig(systemStore.currentSystemId).llm_model || "default");
const currentModelLabel = computed(() => (currentModel.value === "default" ? "默认" : currentModel.value));


function setBackend(k, v) {
  configStore.patchBackend({ [k]: v });
}

async function toggleSttEnabled() {
  const prev = !!configStore.shared.stt_enabled;
  const next = !prev;
  configStore.patchShared({ stt_enabled: next });
  try {
    const patch = buildBackendPatchFromUiConfig(configStore.config);
    await apiSubmit(configStore.backend.http_base, patch);
  } catch {
    configStore.patchShared({ stt_enabled: prev });
  }
}

</script>

<template>
  <div class="app-shell">
    <div class="shell-inner">
      <div class="topbar">
        <div class="brand">
          <span class="brand-dot"></span>
          <span>设置</span>
        </div>
        <div class="top-actions">
          <button class="px-btn" @click="router.push('/')">返回</button>
        </div>
      </div>

      <div class="workspace-viewport">
        <div class="work-grid" style="grid-template-columns: 1fr">
          <div class="main-rail" style="max-width: 900px">
            <div class="panel box">
              <div class="h1">连接</div>
              <div class="p">
                WS：{{ backendStore.wsConnected ? "已连接" : "未连接" }}（{{ backendStore.wsUrl || "—" }}）
              </div>
              <div class="p">系统：{{ systemName }} · 模型：{{ currentModelLabel }}</div>

              <div class="split"></div>

              <SettingRow title="数据源" desc="连接 5000 + WS">
                <select class="px-select" :value="configStore.backend.mode" @change="(e) => setBackend('mode', e.target.value)">
                  <option value="real">后端</option>
                </select>
              </SettingRow>

              <SettingRow title="HTTP Base" desc="例如：http://127.0.0.1:5000">
                <input class="px-input" :value="configStore.backend.http_base" @change="(e) => setBackend('http_base', e.target.value)" />
              </SettingRow>

              <SettingRow title="WS URL" desc="例如：ws://127.0.0.1:10003">
                <input class="px-input" :value="configStore.backend.ws_url" @change="(e) => setBackend('ws_url', e.target.value)" />
              </SettingRow>

              <div class="split"></div>

              <SettingRow title="语音总开关" desc="只控制录音开关，不关闭系统">
                <button class="toggle-switch" :class="{ on: configStore.shared.stt_enabled }" @click="toggleSttEnabled">
                  <span class="toggle-knob"></span>
                </button>
              </SettingRow>

              <div class="btnrow">
                <button class="px-btn" @click="configStore.resetAll()">重置本地配置</button>
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.box {
  padding: 12px;
}
.h1 {
  font-weight: 780;
  margin-bottom: 6px;
  color: var(--text-0);
}
.p {
  color: var(--text-1);
  font-size: 12px;
  line-height: 1.5;
}
.split {
  height: 1px;
  background: var(--stroke);
  opacity: 0.85;
  margin: 10px 0;
}
.btnrow {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
</style>
