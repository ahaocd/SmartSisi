import assert from "node:assert/strict";
import {
  apiGetMemberList,
  apiBrowserCheck,
  apiGetModels,
  apiChatCompletions,
  apiGetMsg,
  apiAdoptMsg,
  apiToGreet,
  apiTransparentPass
} from "../src/api/sisiApi.js";

const calls = [];
const makeRes = (body) => ({
  ok: true,
  headers: { get: () => "application/json" },
  json: async () => body,
  text: async () => JSON.stringify(body)
});

globalThis.fetch = async (url, opts = {}) => {
  calls.push({ url, opts });
  return makeRes({ ok: true });
};

const base = "http://127.0.0.1:5000";
await apiGetMemberList(base);
await apiBrowserCheck(base);
await apiGetModels(base);
await apiChatCompletions(base, { model: "sisi", messages: [{ role: "user", content: "ping" }], stream: false });
await apiChatCompletions(base, { model: "sisi", messages: [{ role: "user", content: "ping" }], stream: false }, { useProxyPath: true });
await apiGetMsg(base, { username: "User" });
await apiAdoptMsg(base, { id: 1 });
await apiToGreet(base, { username: "User", observation: "hello" });
await apiTransparentPass(base, { user: "User", text: "ping", audio: "" });

assert.equal(calls[0].url, `${base}/api/get-member-list`);
assert.equal(calls[0].opts.method, "POST");
assert.equal(calls[1].url, `${base}/api/browser-check`);
assert.equal(calls[1].opts.method, "GET");
assert.equal(calls[2].url, `${base}/v1/models`);
assert.equal(calls[2].opts.method, "GET");
assert.equal(calls[3].url, `${base}/v1/chat/completions`);
assert.equal(calls[3].opts.method, "POST");
assert.equal(calls[4].url, `${base}/api/send/v1/chat/completions`);
assert.equal(calls[4].opts.method, "POST");
assert.equal(calls[5].url, `${base}/api/get-msg`);
assert.equal(calls[5].opts.method, "POST");
assert.equal(calls[6].url, `${base}/api/adopt_msg`);
assert.equal(calls[6].opts.method, "POST");
assert.equal(calls[7].url, `${base}/to_greet`);
assert.equal(calls[7].opts.method, "POST");
assert.equal(calls[8].url, `${base}/transparent_pass`);
assert.equal(calls[8].opts.method, "POST");
