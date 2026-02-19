import { defineStore } from "pinia";

const LS_KEY = "smartsisi_config_v1";

function inferDefaultHttpBase() {
  try {
    if (typeof window !== "undefined" && window.location && window.location.origin) {
      return window.location.origin;
    }
  } catch {}
  return "http://127.0.0.1:5000";
}

function clamp(n, min, max) {
  return Math.min(max, Math.max(min, n));
}

function defaultConfig() {
  return {
    backend: {
      mode: "real",
      http_base: inferDefaultHttpBase(),
      ws_url: "ws://127.0.0.1:10003"
    },
    shared: {
      active_audio_system_id: "sisi",
      audio_policy: "active_only",
      ducking: false,

      // ASR / STT (UI contract; real device list comes from backend WS)
      stt_enabled: true,
      stt_engine: "whisper",
      stt_device: "default",
      stt_language: "zh-CN",
      stt_sample_rate: 16000,

      // TTS (UI contract; real voice list comes from backend WS)
      tts_enabled: true,
      tts_engine: "edge",
      tts_voice: "default",
      tts_rate: 1.0,
      tts_volume: 80,

      // Realtime / input
      realtime_audio_enabled: false,
      ptt_enabled: false,
      duplex_mode: "half",
      image_input_enabled: true,

      // Wake / interrupt / autoplay
      wake_enabled: false,
      wake_word: "柳思思",
      interrupt_enabled: true,
      interrupt_mode: "barge_in",
      autoplay_enabled: false, // 自动播放（后端：source.automatic_player_status）
      qa_autoplay_enabled: false // QA 自动播放
    },
    systems: {
      sisi: {
        llm_provider: "default",
        llm_model: "default",
        system_prompt: "",

        memory_enabled: true,
        tool_enabled: true,
        mcp_enabled: false,
        skills_enabled: false
      },
      liuye: {
        llm_provider: "default",
        llm_model: "default",
        system_prompt: "",

        memory_enabled: true,
        tool_enabled: true,
        mcp_enabled: true,
        skills_enabled: true
      }
    },
    models: {
      agent: { provider: "default", model: "default" },
      guild: { provider: "default", model: "default" }
    },
    prompts: {
      global_prompt: "",
      cortex_prompt: "",
      memory_prompt: ""
    },
    appearance: {
      density: "normal",
      pixel_accent: true,
      motion_enabled: true,
      dock_mode: "auto", // auto | expand | collapse

      background_enabled: false,
      background_rev: 0,
      background_dim: 0.35, // 0..0.8
      background_blur: 10, // 0..18
      colorway_mode: "default", // default | dopamine202
      colorway_seed: 202, // deterministic palette seed
      colorway_variant: 0, // click-to-cycle palette index

      // Ink / brush background FX (canvas)
      inkfx_enabled: true,
      inkfx_intensity: 1.2, // 0.2..2.0
      inkfx_keyboard_mode: "all", // all | hotkeys | none
      inkfx_blend: "multiply", // multiply | overlay | screen
      inkfx_color_mode: "ink+accent" // ink+accent
    }
  };
}

function normalize(cfg) {
  const d = defaultConfig();
  const out = { ...d, ...(cfg || {}) };
  out.backend = { ...d.backend, ...(cfg?.backend || {}) };
  out.shared = { ...d.shared, ...(cfg?.shared || {}) };
  out.systems = {
    sisi: { ...d.systems.sisi, ...(cfg?.systems?.sisi || {}) },
    liuye: { ...d.systems.liuye, ...(cfg?.systems?.liuye || {}) }
  };
  out.models = { ...d.models, ...(cfg?.models || {}) };
  out.models.agent = { ...d.models.agent, ...(cfg?.models?.agent || {}) };
  out.models.guild = { ...d.models.guild, ...(cfg?.models?.guild || {}) };
  out.prompts = { ...d.prompts, ...(cfg?.prompts || {}) };
  out.appearance = { ...d.appearance, ...(cfg?.appearance || {}) };

  out.shared.tts_rate = clamp(Number(out.shared.tts_rate) || 1, 0.5, 2);
  out.shared.tts_volume = clamp(Number(out.shared.tts_volume) || 80, 0, 100);
  out.shared.stt_sample_rate = [16000, 48000].includes(Number(out.shared.stt_sample_rate)) ? Number(out.shared.stt_sample_rate) : 16000;
  if (!["barge_in", "soft", "off"].includes(out.shared.interrupt_mode)) out.shared.interrupt_mode = "barge_in";
  if (!["half", "full"].includes(String(out.shared.duplex_mode || ""))) {
    out.shared.duplex_mode = out.shared.ptt_enabled ? "half" : "full";
  }
  out.shared.ptt_enabled = out.shared.duplex_mode === "half";
  out.shared.realtime_audio_enabled = !!out.shared.stt_enabled;

  if (!["sisi", "liuye"].includes(out.shared.active_audio_system_id)) out.shared.active_audio_system_id = "sisi";
  if (!["active_only"].includes(out.shared.audio_policy)) out.shared.audio_policy = "active_only";

  if (out.backend.mode !== "real") out.backend.mode = "real";
  if (typeof out.backend.http_base !== "string") out.backend.http_base = d.backend.http_base;
  if (typeof out.backend.ws_url !== "string") out.backend.ws_url = d.backend.ws_url;

  if (!["compact", "normal"].includes(out.appearance.density)) out.appearance.density = "normal";
  if (!["auto", "expand", "collapse"].includes(out.appearance.dock_mode)) out.appearance.dock_mode = "auto";

  out.appearance.background_rev = Math.max(0, Number(out.appearance.background_rev) || 0);
  out.appearance.background_dim = clamp(Number(out.appearance.background_dim) || 0.35, 0, 0.8);
  out.appearance.background_blur = clamp(Number(out.appearance.background_blur) || 10, 0, 18);
  if (!["default", "dopamine202"].includes(out.appearance.colorway_mode)) out.appearance.colorway_mode = "default";
  out.appearance.colorway_seed = Math.max(1, Math.floor(Number(out.appearance.colorway_seed) || 202));
  out.appearance.colorway_variant = Math.max(0, Math.floor(Number(out.appearance.colorway_variant) || 0));

  out.appearance.inkfx_enabled = !!out.appearance.inkfx_enabled;
  out.appearance.inkfx_intensity = clamp(Number(out.appearance.inkfx_intensity) || 1.2, 0.2, 2.0);
  if (!["all", "hotkeys", "none"].includes(out.appearance.inkfx_keyboard_mode)) out.appearance.inkfx_keyboard_mode = "all";
  if (!["multiply", "overlay", "screen"].includes(out.appearance.inkfx_blend)) out.appearance.inkfx_blend = "multiply";
  if (!["ink+accent"].includes(out.appearance.inkfx_color_mode)) out.appearance.inkfx_color_mode = "ink+accent";

  return out;
}

export const useConfigStore = defineStore("config", {
  state: () => ({
    config: normalize(null),
    loaded: false,
    backendSnapshot: { config_json: null, system_conf: null }
  }),
  getters: {
    backend(state) {
      return state.config.backend;
    },
    shared(state) {
      return state.config.shared;
    },
    appearance(state) {
      return state.config.appearance;
    },
    models(state) {
      return state.config.models;
    },
    prompts(state) {
      return state.config.prompts;
    },
    systemConfig: (state) => (systemId) => state.config.systems[systemId] || state.config.systems.sisi
  },
  actions: {
    load() {
      if (this.loaded) return;
      try {
        const raw = localStorage.getItem(LS_KEY);
        if (raw) this.config = normalize(JSON.parse(raw));
      } catch {
        this.config = normalize(null);
      }
      this.loaded = true;
    },
    save() {
      try {
        localStorage.setItem(LS_KEY, JSON.stringify(this.config));
      } catch {}
    },
    patchBackend(patch) {
      this.config.backend = normalize({ backend: { ...this.config.backend, ...(patch || {}) } }).backend;
      this.save();
    },
    patchShared(patch) {
      this.config.shared = normalize({ shared: { ...this.config.shared, ...(patch || {}) } }).shared;
      this.save();
    },
    patchSystem(systemId, patch) {
      if (!["sisi", "liuye"].includes(systemId)) return;
      this.config.systems[systemId] = normalize({
        systems: { [systemId]: { ...this.config.systems[systemId], ...(patch || {}) } }
      }).systems[systemId];
      this.save();
    },
    patchAppearance(patch) {
      this.config.appearance = normalize({ appearance: { ...this.config.appearance, ...(patch || {}) } }).appearance;
      this.save();
    },
    patchModels(patch) {
      this.config.models = normalize({ models: { ...this.config.models, ...(patch || {}) } }).models;
      this.save();
    },
    patchPrompts(patch) {
      this.config.prompts = normalize({ prompts: { ...this.config.prompts, ...(patch || {}) } }).prompts;
      this.save();
    },
    setBackendSnapshot(payload) {
      const cfg = payload && typeof payload === "object" ? payload : {};
      this.backendSnapshot = {
        config_json: cfg.config_json || null,
        system_conf: cfg.system_conf || null
      };
    },
    resetAll() {
      this.config = normalize(null);
      this.save();
    }
  }
});
