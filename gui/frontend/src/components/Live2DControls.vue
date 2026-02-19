<script setup>
import { computed, ref } from "vue";
import SettingRow from "./SettingRow.vue";
import { getIcon } from "../ui/icons";

const remember = ref(false);

function iconHtml(name) {
  return getIcon("live2d", name);
}

function clickWidgetTool(toolId) {
  const el = document.getElementById(`waifu-tool-${toolId}`);
  if (!el) return false;
  el.click();
  return true;
}

function nextModel() {
  clickWidgetTool("switch-model");
}

function randomTexture() {
  clickWidgetTool("switch-texture");
}

function resetModel() {
  try {
    localStorage.removeItem("modelId");
    localStorage.removeItem("modelTexturesId");
    localStorage.removeItem("waifu-display");
  } catch {}
  location.reload();
}

try {
  remember.value = localStorage.getItem("smartsisi_live2d_remember") === "1";
} catch {}

function setRemember(v) {
  remember.value = v;
  try {
    localStorage.setItem("smartsisi_live2d_remember", v ? "1" : "0");
  } catch {}
}

const rememberDesc = computed(() => (remember.value ? "关闭页面后仍保持当前人物/换装" : "每次打开随机"));
</script>

<template>
  <div class="wrap">
    <div class="title">
      <div class="t1">角色（Live2D）</div>
      <div class="t2">展示层：不挡输入区</div>
    </div>

    <div class="grid">
      <SettingRow title="记住选择" :desc="rememberDesc">
        <button class="toggle-switch" :class="{ on: remember }" @click="setRemember(!remember)">
          <span class="toggle-knob"></span>
        </button>
      </SettingRow>

      <SettingRow title="换人 / 换装 / 重置" desc="按钮会触发 live2d-widget 内置工具（前端脚本）。">
        <div class="btns">
          <button class="icon-btn" title="换人" @click="nextModel">
            <span class="ico" aria-hidden="true" v-html="iconHtml('next')"></span>
          </button>
          <button class="icon-btn" title="换装" @click="randomTexture">
            <span class="ico" aria-hidden="true" v-html="iconHtml('outfit')"></span>
          </button>
          <button class="icon-btn" title="重置" @click="resetModel">
            <span class="ico" aria-hidden="true" v-html="iconHtml('reset')"></span>
          </button>
        </div>
      </SettingRow>
    </div>

    <div class="tip">
      Live2D-widget 是前端加载的开源脚本；这里的按钮只负责“点它的内置按钮”。<br />
      下一阶段：把 speaking/thinking/listening 等状态映射到角色动作。
    </div>
  </div>
</template>

<style scoped>
.wrap {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.title {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}
.t1 {
  font-weight: 900;
  letter-spacing: 0.2px;
}
.t2 {
  font-size: 11px;
  color: rgba(255, 255, 255, 0.6);
}

.grid {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.btns {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.icon-btn {
  width: 36px;
  height: 34px;
  border-radius: 10px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  background: rgba(0, 0, 0, 0.22);
  color: rgba(255, 255, 255, 0.9);
  cursor: pointer;
  display: grid;
  place-items: center;
  box-shadow: 2px 2px 0 rgba(0, 0, 0, 0.3);
}
.icon-btn:hover {
  border-color: rgba(255, 255, 255, 0.26);
  background: rgba(0, 0, 0, 0.28);
}

.ico :deep(svg) {
  width: 16px;
  height: 16px;
  display: block;
}

.tip {
  padding: 10px 10px;
  border-radius: 12px;
  border: 1px dashed rgba(255, 255, 255, 0.16);
  background: rgba(0, 0, 0, 0.12);
  color: rgba(255, 255, 255, 0.72);
  line-height: 1.45;
  font-size: 12px;
}
</style>
