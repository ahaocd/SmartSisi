function joinUrl(base, path) {
  const b = String(base || "").replace(/\/+$/, "");
  const p = String(path || "").replace(/^\/+/, "");
  return `${b}/${p}`;
}

async function readJsonOrText(res) {
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return await res.json();
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}

function unwrapV1(payload, fallback = "request failed") {
  if (!payload || typeof payload !== "object") {
    throw new Error(fallback);
  }
  if (payload.success === true) {
    return payload.data || {};
  }
  const err = payload.error || {};
  const msg = String(err.message || fallback || "request failed");
  const e = new Error(msg);
  e.code = err.code || "API_ERROR";
  e.detail = err.detail;
  e.trace_id = payload.trace_id;
  throw e;
}

async function requestV1(httpBase, path, { method = "GET", headers, body } = {}) {
  const url = joinUrl(httpBase, path);
  const res = await fetch(url, {
    method,
    headers: headers || {},
    body
  });
  const payload = await readJsonOrText(res);
  if (!res.ok) {
    if (payload && typeof payload === "object") {
      return unwrapV1(payload, `${path} failed: ${res.status}`);
    }
    throw new Error(`${path} failed: ${res.status}`);
  }
  return unwrapV1(payload, `${path} failed`);
}

export async function apiGetData(httpBase) {
  const url = joinUrl(httpBase, "/api/get-data");
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) throw new Error(`get-data failed: ${res.status}`);
  const data = await readJsonOrText(res);
  if (typeof data === "string") {
    try {
      return JSON.parse(data);
    } catch {
      throw new Error("get-data returned non-json text");
    }
  }
  return data;
}

export async function apiSubmit(httpBase, config) {
  const url = joinUrl(httpBase, "/api/submit");
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ config })
  });
  if (!res.ok) throw new Error(`submit failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiGetAllConfig(httpBase) {
  const url = joinUrl(httpBase, "/api/config/all");
  const res = await fetch(url, { method: "GET" });
  if (!res.ok) throw new Error(`config/all get failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiSaveAllConfig(httpBase, payload) {
  const url = joinUrl(httpBase, "/api/config/all");
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {})
  });
  if (!res.ok) throw new Error(`config/all save failed: ${res.status}`);
  return await readJsonOrText(res);
}

async function postNoBody(httpBase, path) {
  const url = joinUrl(httpBase, path);
  const res = await fetch(url, { method: "POST" });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiStartLive(httpBase) {
  return await postNoBody(httpBase, "/api/start-live");
}

export async function apiStopLive(httpBase) {
  return await postNoBody(httpBase, "/api/stop-live");
}

export async function apiGetRunStatus(httpBase) {
  return await postNoBody(httpBase, "/api/get_run_status");
}

export async function apiSendText(httpBase, { username, msg }) {
  const url = joinUrl(httpBase, "/api/send");
  const body = new URLSearchParams();
  body.set("data", JSON.stringify({ username, msg }));
  const res = await fetch(url, { method: "POST", body });
  if (!res.ok) throw new Error(`send failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiToWake(httpBase, payload = {}) {
  const url = joinUrl(httpBase, "/to_wake");
  const body = {
    username: "User",
    observation: "",
    ...(payload || {})
  };
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`to_wake failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiToStopTalking(httpBase, payload = {}) {
  const url = joinUrl(httpBase, "/to_stop_talking");
  const body = {
    username: "User",
    text: "你好，请说？",
    observation: "",
    ...(payload || {})
  };
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`to_stop_talking failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiGetMemberList(httpBase) {
  return await postNoBody(httpBase, "/api/get-member-list");
}

export async function apiBrowserCheck(httpBase) {
  const url = joinUrl(httpBase, "/api/browser-check");
  const res = await fetch(url, { method: "GET" });
  if (!res.ok) throw new Error(`browser-check failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiGetModels(httpBase) {
  const url = joinUrl(httpBase, "/v1/models");
  const res = await fetch(url, { method: "GET" });
  if (!res.ok) throw new Error(`v1/models failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiChatCompletions(httpBase, payload = {}, options = {}) {
  const path = options?.useProxyPath ? "/api/send/v1/chat/completions" : "/v1/chat/completions";
  const url = joinUrl(httpBase, path);
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {})
  });
  if (!res.ok) throw new Error(`chat/completions failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiGetMsg(httpBase, payload = {}) {
  const url = joinUrl(httpBase, "/api/get-msg");
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {})
  });
  if (!res.ok) throw new Error(`get-msg failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiSetSystemMode(httpBase, mode) {
  const url = joinUrl(httpBase, "/api/system/mode");
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ mode })
  });
  if (!res.ok) throw new Error(`system/mode failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiAdoptMsg(httpBase, payload = {}) {
  const url = joinUrl(httpBase, "/api/adopt_msg");
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {})
  });
  if (!res.ok) throw new Error(`adopt_msg failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiToGreet(httpBase, payload = {}) {
  const url = joinUrl(httpBase, "/to_greet");
  const body = {
    username: "User",
    observation: "",
    ...(payload || {})
  };
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`to_greet failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiTransparentPass(httpBase, payload = {}) {
  const url = joinUrl(httpBase, "/transparent_pass");
  const body = {
    user: "User",
    text: "",
    audio: "",
    ...(payload || {})
  };
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body)
  });
  if (!res.ok) throw new Error(`transparent_pass failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiGetTtsVoices(httpBase) {
  const url = joinUrl(httpBase, "/api/tts/voices");
  const res = await fetch(url, { method: "GET" });
  if (!res.ok) throw new Error(`tts voices get failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiSetTtsVoices(httpBase, payload = {}) {
  const url = joinUrl(httpBase, "/api/tts/voices");
  const res = await fetch(url, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {})
  });
  if (!res.ok) throw new Error(`tts voices set failed: ${res.status}`);
  return await readJsonOrText(res);
}

export async function apiV1UploadFile(httpBase, file) {
  const fd = new FormData();
  fd.append("file", file);
  return await requestV1(httpBase, "/api/v1/files/upload", { method: "POST", body: fd });
}

export async function apiV1RegisterUrl(httpBase, payload = {}) {
  return await requestV1(httpBase, "/api/v1/files/register-url", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {})
  });
}

export async function apiV1GetFile(httpBase, fileId) {
  return await requestV1(httpBase, `/api/v1/files/${encodeURIComponent(String(fileId || ""))}`, { method: "GET" });
}

export async function apiV1DeleteFile(httpBase, fileId) {
  return await requestV1(httpBase, `/api/v1/files/${encodeURIComponent(String(fileId || ""))}`, { method: "DELETE" });
}

export async function apiV1SendMultimodalMessage(httpBase, payload = {}) {
  return await requestV1(httpBase, "/api/v1/chat/messages", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {})
  });
}

export async function apiV1RealtimeSession(httpBase, payload = {}) {
  return await requestV1(httpBase, "/api/v1/realtime/session", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {})
  });
}

export async function apiV1RealtimeEvent(httpBase, payload = {}) {
  return await requestV1(httpBase, "/api/v1/realtime/event", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(payload || {})
  });
}
