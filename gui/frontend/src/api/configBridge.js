function isObject(v) {
  return v != null && typeof v === "object" && !Array.isArray(v);
}

function toBool(v, fallback) {
  if (typeof v === "boolean") return v;
  if (v === "true" || v === "1" || v === 1) return true;
  if (v === "false" || v === "0" || v === 0) return false;
  return fallback;
}

function toNumber(v, fallback) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function toStringSafe(v, fallback) {
  if (typeof v === "string") return v;
  if (v == null) return fallback;
  return String(v);
}

function deepMerge(target, patch) {
  if (patch == null || typeof patch !== "object" || Array.isArray(patch)) return target;
  for (const [k, v] of Object.entries(patch)) {
    if (v && typeof v === "object" && !Array.isArray(v)) {
      if (!target[k] || typeof target[k] !== "object" || Array.isArray(target[k])) target[k] = {};
      deepMerge(target[k], v);
    } else {
      target[k] = v;
    }
  }
  return target;
}

function flattenLeaves(obj, prefix = "", out = []) {
  if (Array.isArray(obj)) {
    if (prefix) out.push(prefix);
    return out;
  }
  if (!isObject(obj)) {
    if (prefix) out.push(prefix);
    return out;
  }
  const keys = Object.keys(obj);
  if (!keys.length) {
    if (prefix) out.push(prefix);
    return out;
  }
  for (const k of keys) {
    const p = prefix ? `${prefix}.${k}` : k;
    flattenLeaves(obj[k], p, out);
  }
  return out;
}

const MAPPED_BACKEND_PATHS = [
  "source.ASR_mode",
  "source.record.enabled",
  "source.record.device",
  "source.record.sample_rate",
  "source.wake_word_enabled",
  "source.wake_word",
  "source.automatic_player_status",
  "interact.playSound",
  "monitoring.voice_interrupt_enabled",
  "attribute.voice"
];

const SHARED_KEY_TO_BACKEND_PATH = {
  stt_engine: "source.ASR_mode",
  stt_enabled: "source.record.enabled",
  stt_device: "source.record.device",
  stt_sample_rate: "source.record.sample_rate",
  wake_enabled: "source.wake_word_enabled",
  wake_word: "source.wake_word",
  autoplay_enabled: "source.automatic_player_status",
  tts_enabled: "interact.playSound",
  interrupt_enabled: "monitoring.voice_interrupt_enabled",
  tts_voice: "attribute.voice"
};

export function mapBackendConfigToUiPatch(backendConfig, currentUiConfig = {}) {
  const source = isObject(backendConfig?.source) ? backendConfig.source : {};
  const record = isObject(source.record) ? source.record : {};
  const interact = isObject(backendConfig?.interact) ? backendConfig.interact : {};
  const monitoring = isObject(backendConfig?.monitoring) ? backendConfig.monitoring : {};
  const attribute = isObject(backendConfig?.attribute) ? backendConfig.attribute : {};
  const currentShared = isObject(currentUiConfig?.shared) ? currentUiConfig.shared : {};

  const sharedPatch = {};

  if (Object.prototype.hasOwnProperty.call(source, "ASR_mode")) {
    sharedPatch.stt_engine = toStringSafe(source.ASR_mode, currentShared.stt_engine || "whisper");
  }
  if (Object.prototype.hasOwnProperty.call(record, "enabled")) {
    sharedPatch.stt_enabled = toBool(record.enabled, !!currentShared.stt_enabled);
    sharedPatch.realtime_audio_enabled = !!sharedPatch.stt_enabled;
  }
  if (Object.prototype.hasOwnProperty.call(record, "device")) {
    sharedPatch.stt_device = toStringSafe(record.device, currentShared.stt_device || "default");
  }
  if (Object.prototype.hasOwnProperty.call(record, "sample_rate")) {
    const sr = toNumber(record.sample_rate, currentShared.stt_sample_rate || 16000);
    sharedPatch.stt_sample_rate = [16000, 48000].includes(sr) ? sr : currentShared.stt_sample_rate || 16000;
  }
  if (Object.prototype.hasOwnProperty.call(source, "wake_word_enabled")) {
    sharedPatch.wake_enabled = toBool(source.wake_word_enabled, !!currentShared.wake_enabled);
  }
  if (Object.prototype.hasOwnProperty.call(source, "wake_word")) {
    sharedPatch.wake_word = toStringSafe(source.wake_word, currentShared.wake_word || "");
  }
  if (Object.prototype.hasOwnProperty.call(source, "automatic_player_status")) {
    sharedPatch.autoplay_enabled = toBool(source.automatic_player_status, !!currentShared.autoplay_enabled);
  }
  if (Object.prototype.hasOwnProperty.call(interact, "playSound")) {
    sharedPatch.tts_enabled = toBool(interact.playSound, !!currentShared.tts_enabled);
  }
  if (Object.prototype.hasOwnProperty.call(monitoring, "voice_interrupt_enabled")) {
    sharedPatch.interrupt_enabled = toBool(monitoring.voice_interrupt_enabled, !!currentShared.interrupt_enabled);
  }
  if (Object.prototype.hasOwnProperty.call(attribute, "voice")) {
    sharedPatch.tts_voice = toStringSafe(attribute.voice, currentShared.tts_voice || "default");
  }

  return {
    sharedPatch,
    mappedPaths: MAPPED_BACKEND_PATHS
  };
}

export function buildBackendPatchFromUiConfig(uiConfig = {}) {
  const shared = isObject(uiConfig?.shared) ? uiConfig.shared : {};
  const sampleRate = [16000, 48000].includes(Number(shared.stt_sample_rate)) ? Number(shared.stt_sample_rate) : 16000;
  const sttEnabled =
    typeof shared.stt_enabled === "boolean" ? shared.stt_enabled : !!shared.realtime_audio_enabled;

  return {
    source: {
      ASR_mode: toStringSafe(shared.stt_engine, "whisper"),
      wake_word_enabled: !!shared.wake_enabled,
      wake_word: toStringSafe(shared.wake_word, ""),
      automatic_player_status: !!shared.autoplay_enabled,
      record: {
        enabled: !!sttEnabled,
        device: toStringSafe(shared.stt_device, "default"),
        sample_rate: sampleRate
      }
    },
    interact: {
      playSound: !!shared.tts_enabled
    },
    monitoring: {
      voice_interrupt_enabled: !!shared.interrupt_enabled
    },
    attribute: {
      voice: toStringSafe(shared.tts_voice, "default")
    }
  };
}

export function mergeUiPatchIntoBackendConfig(rawConfig = {}, uiConfig = {}) {
  const next = JSON.parse(JSON.stringify(rawConfig || {}));
  const patch = buildBackendPatchFromUiConfig(uiConfig);
  return deepMerge(next, patch);
}

export function analyzeConfigAlignment(backendConfig = {}, uiConfig = {}) {
  const shared = isObject(uiConfig?.shared) ? uiConfig.shared : {};
  const sharedKeys = Object.keys(shared);
  const frontendOnlyShared = sharedKeys.filter((k) => !Object.prototype.hasOwnProperty.call(SHARED_KEY_TO_BACKEND_PATH, k));

  const backendLeaves = [];
  for (const section of ["source", "interact", "monitoring", "attribute"]) {
    if (!Object.prototype.hasOwnProperty.call(backendConfig || {}, section)) continue;
    flattenLeaves(backendConfig[section], section, backendLeaves);
  }

  const mappedSet = new Set(MAPPED_BACKEND_PATHS);
  const backendOnly = Array.from(new Set(backendLeaves)).filter((p) => !mappedSet.has(p));

  return {
    mapped: [...MAPPED_BACKEND_PATHS],
    frontendOnly: [
      ...frontendOnlyShared.map((k) => `shared.${k}`),
      "systems.*",
      "models.*",
      "prompts.*",
      "appearance.*"
    ],
    backendOnly,
    notes: [
      "source/interact/monitoring/attribute sections are compared for backend gaps",
      "systems/models/prompts/appearance are frontend domains without direct backend mapping"
    ]
  };
}
