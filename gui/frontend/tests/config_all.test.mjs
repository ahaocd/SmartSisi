import assert from "node:assert/strict";
import { mergeUiPatchIntoBackendConfig } from "../src/api/configBridge.js";

const raw = { source: { ASR_mode: "whisper" }, attribute: { voice: "v1" } };
const ui = { shared: { stt_engine: "sherpa", tts_voice: "v2", wake_enabled: true } };
const next = mergeUiPatchIntoBackendConfig(raw, ui);

assert.equal(next.source.ASR_mode, "sherpa");
assert.equal(next.attribute.voice, "v2");
assert.equal(next.source.wake_word_enabled, true);

const raw2 = { source: { record: { enabled: false } } };
const ui2 = { shared: { stt_enabled: true } };
const next2 = mergeUiPatchIntoBackendConfig(raw2, ui2);
assert.equal(next2.source.record.enabled, true);
console.log("ok");
