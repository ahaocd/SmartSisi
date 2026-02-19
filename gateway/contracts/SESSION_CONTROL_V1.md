# Session and Control Contract (V1)

## Required Envelope

Every control message should include:

1. `type`
2. `device_id`
3. `session_id`
4. `turn_id`
5. `ts_ms`
6. `priority`

## Control Types

1. `interrupt`
2. `commit_turn`
3. `cancel_turn`
4. `heartbeat`

## Routing Rules

1. Control path must be independent from media queue.
2. `interrupt` must preempt all pending media operations.
3. Unknown control type must be acknowledged as rejected, not silently dropped.

## ACK Rules

1. Every accepted control message returns `ack=true`.
2. Every rejected control message returns `ack=false` and `reason`.
3. ACK must include original `turn_id` and `ts_ms`.

