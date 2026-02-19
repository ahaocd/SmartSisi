import assert from "node:assert/strict";
import { getApiConsoleActions } from "../src/api/apiConsole.js";

const calls = [];
const api = {
  apiGetData: async (...args) => calls.push(["apiGetData", ...args]),
  apiSubmit: async (...args) => calls.push(["apiSubmit", ...args]),
  apiStartLive: async (...args) => calls.push(["apiStartLive", ...args]),
  apiStopLive: async (...args) => calls.push(["apiStopLive", ...args]),
  apiGetRunStatus: async (...args) => calls.push(["apiGetRunStatus", ...args]),
  apiSendText: async (...args) => calls.push(["apiSendText", ...args]),
  apiToWake: async (...args) => calls.push(["apiToWake", ...args]),
  apiToStopTalking: async (...args) => calls.push(["apiToStopTalking", ...args]),
  apiGetMemberList: async (...args) => calls.push(["apiGetMemberList", ...args]),
  apiBrowserCheck: async (...args) => calls.push(["apiBrowserCheck", ...args]),
  apiGetModels: async (...args) => calls.push(["apiGetModels", ...args]),
  apiChatCompletions: async (...args) => calls.push(["apiChatCompletions", ...args]),
  apiGetMsg: async (...args) => calls.push(["apiGetMsg", ...args]),
  apiAdoptMsg: async (...args) => calls.push(["apiAdoptMsg", ...args]),
  apiToGreet: async (...args) => calls.push(["apiToGreet", ...args]),
  apiTransparentPass: async (...args) => calls.push(["apiTransparentPass", ...args])
};

const base = "http://127.0.0.1:5000";
const actions = getApiConsoleActions({ api, httpBase: base });
assert.ok(actions.find((a) => a.id === "browser-check"));
assert.ok(actions.find((a) => a.id === "get-data"));
assert.ok(actions.find((a) => a.id === "send"));

for (const a of actions) await a.run();
assert.equal(calls.length, actions.length);
