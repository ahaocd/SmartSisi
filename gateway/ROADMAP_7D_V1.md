# Gateway 7-Day Execution Plan (V1)

## Day 1 - Contracts Freeze

Deliverables:

1. Freeze device session fields: `device_id`, `session_id`, `turn_id`, `ts_ms`.
2. Freeze control event schema: `interrupt`, `commit_turn`, `cancel_turn`, `heartbeat`.
3. Define required acknowledgements for control path.

Pass criteria:

1. No schema ambiguity in client/server logs.
2. Unknown fields are ignored, not fatal.

## Day 2 - Cross-Network Reachability Baseline

Deliverables:

1. One canonical public gateway endpoint policy.
2. Android always connects to the canonical endpoint with automatic reconnect.
3. `gateway/network/check_endpoints.ps1` validated on host machine.

Pass criteria:

1. Device reconnects automatically after temporary gateway outage.
2. No endpoint rotation or multi-endpoint policy in runtime.

## Day 3 - App Gateway Skeleton

Deliverables:

1. Build `gateway/app` skeleton: session registry + auth guard + route policy.
2. Keep compatibility with existing bridge target ports.
3. Add explicit control-event ack path.

Pass criteria:

1. Existing voice turns still complete.
2. Session lifecycle is observable (`connected`, `active_turn`, `closed`).

## Day 4 - Control Fast Lane

Deliverables:

1. Physically separate control lane from media lane.
2. Keep media lane throughput unchanged.
3. Backpressure policy: control lane must never wait behind audio queue.

Pass criteria:

1. `interrupt` p95 delivery latency improves vs mixed lane baseline.
2. No regression in TTS packet continuity.

## Day 5 - Observability and Safeguards

Deliverables:

1. Metrics: `control_latency_ms`, `tts_first_packet_ms`, `reconnect_ms`, `drop_rate`.
2. Health probes for network and gateway app components.
3. Strict startup guard: fail fast when required gateway/control lane is unavailable.

Pass criteria:

1. Metrics exported every session.
2. Startup fails immediately when contract prerequisites are not met.

## Day 6 - Failure Drills

Deliverables:

1. Simulate weak network, high packet loss, and endpoint outage.
2. Verify automatic reconnect behavior on the same canonical endpoint.
3. Verify control lane still preempts while media degrades.

Pass criteria:

1. No manual intervention required in standard outage scenarios.
2. Recovery to healthy lane under configured timeout window.

## Day 7 - Release Gate

Release checklist:

1. Interrupt latency target met in real-device tests.
2. Canonical public endpoint validated across different networks.
3. No third-party naming in runtime logs.
4. Runtime path is strict single-lane (no fallback endpoint policy).
