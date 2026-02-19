# Sisi Gateway (Single-Repo Execution Lane)

## Goal

Build an always-reachable access layer for Sisi without rewriting the core voice chain.

Target outcome:

1. Device connects to one canonical gateway endpoint.
2. Control events (`interrupt/commit/cancel`) are not blocked by bulk audio traffic.
3. Existing core path stays intact: `pc_stream_queue -> route -> AndroidOutputHub`.

## Non-Negotiables

1. Do not scatter gateway code across unrelated folders.
2. Do not introduce third-party branding into runtime logs/messages.
3. Do not break current WS `9002 -> bridge -> 10001/9001` compatibility.

## Directory Layout

1. `gateway/network/`
2. `gateway/app/`
3. `gateway/contracts/`
4. `gateway/ops/`
5. `gateway/ROADMAP_7D_V1.md`

## Current Execution Entry

1. Android should use one canonical endpoint:
  - device lane: `wss://<public-host>/device`
  - control lane: `wss://<public-host>/control`
2. Connection ownership:
  - Android initiates and maintains WS connection.
  - Sisi server exposes and keeps gateway lanes ready.

## Quick Start

1. Fill `gateway/network/profiles.example.env`.
2. Set Android `gradle.properties`:
  - `sisimoveWsEndpoints=wss://<public-host>/device`
3. Build and install app, then verify runtime log includes selected endpoint.
4. Start app-layer gateway:
  - `powershell -ExecutionPolicy Bypass -File gateway/ops/run_ws_gateway.ps1 -Port 9102 -MediaBackend ws://127.0.0.1:9002 -ControlBackend ws://127.0.0.1:9003`
  - stop: `powershell -ExecutionPolicy Bypass -File gateway/ops/stop_ws_gateway.ps1 -Port 9102`
5. Android endpoint must point to gateway front door:
  - `wss://<public-host>/device`

## Booter Integration (Architecture Baseline)

`core/sisi_booter.py` can now start/stop app-layer gateway as part of one topology lifecycle.

Use `system.conf` keys under `[key]`:

1. `control_lane_enabled`
2. `control_lane_required`
3. `control_tcp_port`
4. `control_ws_port`
5. `transport_health_probe_interval_ms`
6. `gateway_front_door_enabled`
7. `gateway_front_door_host`
8. `gateway_front_door_port`
9. `gateway_media_backend`
10. `gateway_control_backend`
11. `gateway_access_token`
12. `gateway_max_message_bytes`

When `gateway_front_door_enabled=true`, booter starts gateway with the same process lifecycle as media/control TCP-WS bridges and reports status in `[transport] network services status`.
