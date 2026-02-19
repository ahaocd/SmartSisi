# Liuye API Design Plan (v1)

Generated: 2026-02-15

## Non-Negotiable Frontend Rule

Any new backend endpoint added to the frontend must have a simple, human-friendly label shown in the UI. The label should be short, plain language, and easy to understand at a glance.

Example mapping:
- "/api/start-live" -> "Start"
- "/api/stop-live" -> "Stop"
- "/api/config/all" -> "Config"

## Goals

- One clear contract for Liuye, models, guilds, and adventurers.
- REST first, SSE/WS for streaming/events.
- Reuse existing concepts (OpenAI style chat, A2A tools) without breaking.
- Observable: every request can be traced.

## Base Conventions

- Base path: `/api/v1`
- Standard response:

```json
{
  "success": true,
  "data": {},
  "error": null,
  "trace_id": "uuid"
}
```

- Error response:

```json
{
  "success": false,
  "data": null,
  "error": { "code": "BAD_REQUEST", "message": "...", "detail": {} },
  "trace_id": "uuid"
}
```

- Common headers:
  - `Authorization: Bearer ...`
  - `X-Trace-Id: ...`
  - `X-Request-Id: ...`

## Resource Model

- Liuye = primary agent service
- Model Config = provider, model, alias, routing policy
- Guild = orchestrator (tasks, roster, routing)
- Adventurer = agent instance with skills/tools/memory

## 1) Liuye Core API

| Endpoint | Method | Purpose | UI Label (example) |
| --- | --- | --- | --- |
| `/api/v1/liuye/health` | GET | Health check | "Health" |
| `/api/v1/liuye/session` | POST | Create session | "New Chat" |
| `/api/v1/liuye/session/{session_id}` | GET | Get session | "Session" |
| `/api/v1/liuye/session/{session_id}/turn` | POST | Send a turn | "Send" |
| `/api/v1/liuye/invoke/{tool_name}` | POST | Invoke tool | "Use Tool" |
| `/api/v1/liuye/tools` | GET | Tool list | "Tools" |
| `/api/v1/liuye/tools/{tool_name}/metadata` | GET | Tool metadata | "Tool Info" |
| `/api/v1/liuye/memory/search` | POST | Search memory | "Memory Search" |
| `/api/v1/liuye/memory/add` | POST | Add memory | "Save Memory" |
| `/api/v1/liuye/events/subscribe` | GET (SSE) | Event stream | "Live Events" |

### Liuye Turn Request (compatible with chat/completions)

```json
{
  "session_id": "optional",
  "model": "liuye-default",
  "messages": [{"role":"user","content":"..."}],
  "stream": true,
  "metadata": {"user_id":"u1"}
}
```

### Liuye Turn Response (non-stream)

```json
{
  "success": true,
  "data": {
    "reply": "...",
    "session_id": "s1",
    "usage": {"tokens": 123}
  },
  "error": null,
  "trace_id": "..."
}
```

## 2) Model Config API

| Endpoint | Method | Purpose | UI Label (example) |
| --- | --- | --- | --- |
| `/api/v1/models/providers` | GET | Provider list | "Providers" |
| `/api/v1/models/providers` | POST | Add provider | "Add Provider" |
| `/api/v1/models` | GET | Model list | "Models" |
| `/api/v1/models` | POST | Register model | "Add Model" |
| `/api/v1/models/aliases` | GET | Alias list | "Aliases" |
| `/api/v1/models/aliases` | POST | Create alias | "Add Alias" |
| `/api/v1/models/aliases/{alias}` | PATCH | Update alias route | "Edit Alias" |
| `/api/v1/models/validate` | POST | Validate config | "Check" |
| `/api/v1/models/usage` | GET | Usage stats | "Usage" |

### Alias Example

```json
{
  "alias": "liuye-default",
  "route": {
    "provider": "openai",
    "model": "gpt-4.1",
    "policy": {"cost": "medium", "latency": "low"}
  }
}
```

## 3) Guild API (Adventure Guild)

| Endpoint | Method | Purpose | UI Label (example) |
| --- | --- | --- | --- |
| `/api/v1/guilds` | GET | Guild list | "Guilds" |
| `/api/v1/guilds` | POST | Create guild | "New Guild" |
| `/api/v1/guilds/{guild_id}` | GET | Guild detail | "Guild" |
| `/api/v1/guilds/{guild_id}` | PATCH | Update guild | "Edit Guild" |
| `/api/v1/guilds/{guild_id}/roster` | GET | Member list | "Roster" |
| `/api/v1/guilds/{guild_id}/roster` | POST | Invite/join | "Add Member" |
| `/api/v1/guilds/{guild_id}/quests` | GET | Quest list | "Quests" |
| `/api/v1/guilds/{guild_id}/quests` | POST | Create quest | "New Quest" |
| `/api/v1/guilds/{guild_id}/match` | POST | Match/assign | "Assign" |
| `/api/v1/guilds/{guild_id}/events` | GET (SSE) | Event stream | "Guild Live" |

### Quest Example

```json
{
  "title": "Summarize report",
  "input": "...",
  "priority": "high",
  "deadline": "2026-02-20T00:00:00Z",
  "reward": {"type": "points", "value": 50}
}
```

## 4) Adventurer API (Agents)

| Endpoint | Method | Purpose | UI Label (example) |
| --- | --- | --- | --- |
| `/api/v1/adventurers` | GET | Adventurer list | "Adventurers" |
| `/api/v1/adventurers` | POST | Create adventurer | "New Adventurer" |
| `/api/v1/adventurers/{id}` | GET | Adventurer detail | "Adventurer" |
| `/api/v1/adventurers/{id}` | PATCH | Update settings | "Edit" |
| `/api/v1/adventurers/{id}/status` | GET | Live status | "Status" |
| `/api/v1/adventurers/{id}/invoke` | POST | Direct call | "Run" |
| `/api/v1/adventurers/{id}/skills` | GET | Skills list | "Skills" |
| `/api/v1/adventurers/{id}/skills` | POST | Attach skill | "Add Skill" |
| `/api/v1/adventurers/{id}/memory/search` | POST | Memory search | "Memory Search" |
| `/api/v1/adventurers/{id}/memory/add` | POST | Memory add | "Save Memory" |
| `/api/v1/adventurers/{id}/sessions` | GET | Session list | "Sessions" |

## 5) Events and Streaming

- SSE endpoint should stream JSON lines with `type` and `data`.
- Suggested event types: `status`, `reply`, `tool`, `memory`, `error`.

Example SSE payload:

```json
{"type":"reply","data":{"text":"...","phase":"final"}}
```

## 6) Research Checklist

1. Confirm naming and path prefix (`/api/v1` vs `/liuye`).
2. Confirm multi-tenant needs (per-user isolation).
3. Confirm streaming channel choice (SSE vs WS).
4. Define standard auth and rate limits.
5. Decide how A2A tools map into Liuye endpoints.
6. Specify data models (Guild, Adventurer, Quest, ModelAlias).
7. Draft OpenAPI contract + mock server.

## 7) UI Label Guidance (must follow)

- Each API must map to a short label, max 1-3 words.
- Avoid internal jargon in UI labels.
- If label is unclear, add a tooltip, but keep label simple.

