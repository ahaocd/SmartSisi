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

function makeError(message, extra = {}) {
  const err = new Error(message);
  Object.assign(err, extra);
  return err;
}

async function requestV1(httpBase, path, options = {}) {
  const url = joinUrl(httpBase, path);
  const method = String(options.method || "GET").toUpperCase();
  const init = { method };

  if (Object.prototype.hasOwnProperty.call(options, "body")) {
    init.headers = { "content-type": "application/json" };
    init.body = JSON.stringify(options.body ?? {});
  }

  const res = await fetch(url, init);
  const payload = await readJsonOrText(res);

  if (!res.ok && (payload == null || typeof payload !== "object")) {
    throw makeError(`${method} ${path} failed: ${res.status}`, {
      code: "HTTP_ERROR",
      status: res.status,
      response: payload
    });
  }

  return payload;
}

function unwrapV1(payload, fallbackMessage) {
  if (!payload || typeof payload !== "object") {
    throw makeError(fallbackMessage || "Invalid response payload", {
      code: "INVALID_RESPONSE",
      detail: payload
    });
  }

  if (payload.success === true) {
    const data = payload.data ?? {};
    if (data != null && typeof data === "object" && !Array.isArray(data)) {
      return { ...data, trace_id: data.trace_id || payload.trace_id || "" };
    }
    return { value: data, trace_id: payload.trace_id || "" };
  }

  const errorObj = payload.error && typeof payload.error === "object" ? payload.error : {};
  const message = String(errorObj.message || fallbackMessage || "Request failed");
  throw makeError(message, {
    code: errorObj.code || "V1_ERROR",
    trace_id: payload.trace_id || "",
    detail: errorObj.detail ?? {},
    response: payload
  });
}

export async function apiV1GetGuilds(httpBase) {
  const payload = await requestV1(httpBase, "/api/v1/guilds", { method: "GET" });
  return unwrapV1(payload, "Failed to load guild list");
}

export async function apiV1GetGuildDetail(httpBase, guildId) {
  const payload = await requestV1(httpBase, `/api/v1/guilds/${encodeURIComponent(guildId)}`, { method: "GET" });
  return unwrapV1(payload, "Failed to load guild detail");
}

export async function apiV1GetGuildRoster(httpBase, guildId) {
  const payload = await requestV1(httpBase, `/api/v1/guilds/${encodeURIComponent(guildId)}/roster`, { method: "GET" });
  return unwrapV1(payload, "Failed to load guild roster");
}

export async function apiV1GetAdventurers(httpBase) {
  const payload = await requestV1(httpBase, "/api/v1/adventurers", { method: "GET" });
  return unwrapV1(payload, "Failed to load adventurers");
}

export async function apiV1CreateGuildQuest(httpBase, guildId, body = {}) {
  const payload = await requestV1(httpBase, `/api/v1/guilds/${encodeURIComponent(guildId)}/quests`, {
    method: "POST",
    body
  });
  return unwrapV1(payload, "Failed to create guild quest");
}

export async function apiV1DissolveGuild(httpBase, guildId, body = {}) {
  const payload = await requestV1(httpBase, `/api/v1/guilds/${encodeURIComponent(guildId)}/dissolve`, {
    method: "POST",
    body
  });
  return unwrapV1(payload, "Failed to dissolve guild");
}

export async function apiV1InvokeAdventurer(httpBase, advId, body = {}) {
  const payload = await requestV1(httpBase, `/api/v1/adventurers/${encodeURIComponent(advId)}/invoke`, {
    method: "POST",
    body
  });
  return unwrapV1(payload, "Failed to invoke adventurer");
}
