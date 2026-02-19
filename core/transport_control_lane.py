from __future__ import annotations

import threading
import time
from copy import deepcopy
from typing import Dict

from utils import util


class TransportControlCoordinator:
    def __init__(self):
        self._device_aec_available = False
        self._device_ns_available = False
        self._device_agc_available = False
        self._capture_fx_signature = ""
        self._control_apply_lock = threading.Lock()
        self._control_apply_running = False
        self._control_apply_last_ms = 0
        self._control_apply_min_interval_ms = 300
        self._control_order_lock = threading.Lock()
        self._lane_epoch = {}
        self._lane_seq = {}
        self._control_stale_ttl_ms = 15000
        self._wake_hit_handler_lock = threading.Lock()
        self._wake_hit_handler = None
        self._state_lock = threading.Lock()
        self._state = {
            "received": 0,
            "interrupt": 0,
            "commit": 0,
            "heartbeat": 0,
            "wake_hit": 0,
            "unknown": 0,
            "dropped": 0,
            "drop_stale_ts": 0,
            "drop_stale_epoch": 0,
            "drop_stale_seq": 0,
            "errors": 0,
            "last_control_type": "",
            "last_latency_ms": -1,
            "last_source_lane": "",
            "last_action": "",
            "last_ts_ms": 0,
        }

    @staticmethod
    def parse_control_payload(payload_text: str) -> Dict[str, str]:
        fields = {}
        for raw in str(payload_text or "").split(";"):
            if "=" not in raw:
                continue
            key, value = raw.split("=", 1)
            norm_key = key.strip().lower()
            norm_value = value.strip()
            fields[norm_key] = norm_value
            if norm_key == "payload" and norm_value:
                for item in norm_value.split("&"):
                    if "=" not in item:
                        continue
                    sub_key, sub_value = item.split("=", 1)
                    sub_key = sub_key.strip().lower()
                    if not sub_key:
                        continue
                    fields.setdefault(sub_key, sub_value.strip())
        return fields

    @staticmethod
    def _to_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        return str(value or "").strip().lower() in ("1", "true", "yes", "on")

    @staticmethod
    def _to_int(value, default=-1):
        try:
            text = str(value or "").strip()
            if not text:
                return default
            return int(text)
        except Exception:
            return default

    def _check_control_ordering(self, fields: Dict[str, str], source_lane: str, now_ms: int):
        lane = source_lane or "unknown"
        stream = str(fields.get("stream", fields.get("stream_id", "")) or "default").strip() or "default"
        epoch = self._to_int(fields.get("epoch", fields.get("session_epoch", fields.get("wake_epoch", ""))), default=-1)
        seq = self._to_int(fields.get("seq", fields.get("frame_seq", fields.get("control_seq", ""))), default=-1)
        ts_ms = self._to_int(fields.get("ts", ""), default=-1)

        if ts_ms > 0 and now_ms >= ts_ms and (now_ms - ts_ms) > self._control_stale_ttl_ms:
            return True, "stale_ts", epoch, seq, stream

        if epoch < 0 and seq < 0:
            return False, "", epoch, seq, stream

        with self._control_order_lock:
            if epoch >= 0:
                prev_epoch = self._lane_epoch.get(lane, -1)
                if prev_epoch > epoch:
                    return True, "stale_epoch", epoch, seq, stream
                if epoch > prev_epoch:
                    self._lane_epoch[lane] = epoch

            seq_scope_epoch = epoch if epoch >= 0 else self._lane_epoch.get(lane, -1)
            seq_key = f"{lane}:{stream}:{seq_scope_epoch}"
            if seq >= 0:
                prev_seq = self._lane_seq.get(seq_key, -1)
                if prev_seq >= 0 and seq <= prev_seq:
                    return True, "stale_seq", epoch, seq, stream
                self._lane_seq[seq_key] = seq

        return False, "", epoch, seq, stream

    def _update_capture_fx_caps(self, fields: Dict[str, str]) -> bool:
        source = str(fields.get("source", "")).strip().lower()
        has_caps = any(
            key in fields for key in ("aec_available", "ns_available", "agc_available")
        )
        if source != "android_capture_fx" and not has_caps:
            return False

        prev_sig = self._capture_fx_signature

        if "aec_available" in fields:
            self._device_aec_available = self._to_bool(fields.get("aec_available"))
        if "ns_available" in fields:
            self._device_ns_available = self._to_bool(fields.get("ns_available"))
        if "agc_available" in fields:
            self._device_agc_available = self._to_bool(fields.get("agc_available"))

        self._capture_fx_signature = "aec={}|ns={}|agc={}".format(
            int(bool(self._device_aec_available)),
            int(bool(self._device_ns_available)),
            int(bool(self._device_agc_available)),
        )
        if self._capture_fx_signature == prev_sig:
            return False

        util.log(
            1,
            (
                "[transport][capture_fx] source=android_capture_fx aec_available={} ns_available={} "
                "agc_available={} aec_arch=device_primary"
            ).format(
                int(bool(self._device_aec_available)),
                int(bool(self._device_ns_available)),
                int(bool(self._device_agc_available)),
            ),
        )
        return True

    @staticmethod
    def _apply_interrupt_fast_path():
        applied = []
        try:
            from utils.pc_stream_queue import get_pc_stream_queue

            get_pc_stream_queue().stop_all()
            applied.append("pc_stream_stop")
        except Exception:
            pass
        return ",".join(applied) if applied else "none"

    def _dispatch_interrupt_apply_async(self):
        now_ms = int(time.time() * 1000)
        with self._control_apply_lock:
            if self._control_apply_running:
                return "coalesced_running"
            if (now_ms - self._control_apply_last_ms) < self._control_apply_min_interval_ms:
                return "coalesced_recent"
            self._control_apply_running = True
            self._control_apply_last_ms = now_ms

        def _worker():
            try:
                from core.unified_system_controller import get_unified_controller

                get_unified_controller().stop_music()
            except Exception as e:
                util.log(2, f"[transport][control_apply] failed type=interrupt error={str(e)}")
            finally:
                with self._control_apply_lock:
                    self._control_apply_running = False

        threading.Thread(
            target=_worker,
            name="transport-control-stopall",
            daemon=True,
        ).start()
        return "stop_music_async"

    def _count_state(self, *, control_type: str, source_lane: str, latency_ms: int, action: str):
        with self._state_lock:
            self._state["received"] += 1
            if action in ("drop_stale_ts", "drop_stale_epoch", "drop_stale_seq"):
                self._state["dropped"] += 1
                self._state[action] += 1
            if control_type in ("interrupt", "cancel_turn", "cancel"):
                self._state["interrupt"] += 1
            elif control_type in ("commit_turn", "commit"):
                self._state["commit"] += 1
            elif control_type == "heartbeat":
                self._state["heartbeat"] += 1
            elif control_type in ("wake_hit", "wake", "wake_trigger"):
                self._state["wake_hit"] += 1
            else:
                self._state["unknown"] += 1
            self._state["last_control_type"] = control_type
            self._state["last_latency_ms"] = latency_ms
            self._state["last_source_lane"] = source_lane
            self._state["last_action"] = action
            self._state["last_ts_ms"] = int(time.time() * 1000)

    def _count_error(self):
        with self._state_lock:
            self._state["errors"] += 1
            self._state["last_ts_ms"] = int(time.time() * 1000)

    def set_wake_hit_handler(self, handler):
        with self._wake_hit_handler_lock:
            self._wake_hit_handler = handler

    def _dispatch_wake_hit(self, fields: Dict[str, str], source_lane: str):
        with self._wake_hit_handler_lock:
            handler = self._wake_hit_handler
        if handler is None:
            return False, "wake_hit_unbound"
        try:
            handled = bool(handler(fields=fields, source_lane=source_lane))
            if handled:
                return True, "wake_hit_applied"
            return True, "wake_hit_ignored"
        except Exception as e:
            util.log(2, f"[transport][wake_hit] handler failed error={str(e)}")
            return False, "wake_hit_error"

    def handle_control_payload(self, payload_text: str, *, source_lane: str = "unknown") -> Dict[str, str]:
        fields = self.parse_control_payload(payload_text)
        control_type = str(fields.get("type", "")).strip().lower()
        stream_id = str(fields.get("stream", fields.get("stream_id", ""))).strip()
        priority = str(fields.get("priority", "")).strip().lower()
        ts_raw = str(fields.get("ts", "")).strip()
        capture_fx_updated = self._update_capture_fx_caps(fields)

        now_ms = int(time.time() * 1000)
        latency_ms = -1
        if ts_raw.isdigit():
            latency_ms = max(0, now_ms - int(ts_raw))

        drop, drop_reason, order_epoch, order_seq, order_stream = self._check_control_ordering(
            fields,
            source_lane=source_lane,
            now_ms=now_ms,
        )

        util.log(
            1,
            f"[transport][control_rx] type={control_type or 'unknown'} stream={stream_id} priority={priority or 'normal'} lane={source_lane} latency_ms={latency_ms} epoch={order_epoch} seq={order_seq}",
        )

        if drop:
            action = f"drop_{drop_reason}"
            self._count_state(
                control_type=control_type or "unknown",
                source_lane=source_lane,
                latency_ms=latency_ms,
                action=action,
            )
            util.log(
                1,
                f"[transport][control_drop] type={control_type or 'unknown'} lane={source_lane} stream={order_stream} action={action} epoch={order_epoch} seq={order_seq}",
            )
            return {
                "ok": False,
                "dropped": True,
                "action": action,
                "control_type": control_type or "unknown",
            }

        action = "noop"
        try:
            if control_type in ("interrupt", "cancel_turn", "cancel"):
                fast_path = self._apply_interrupt_fast_path()
                async_action = self._dispatch_interrupt_apply_async()
                action = async_action if fast_path == "none" else f"{async_action}+{fast_path}"
            elif control_type in ("commit_turn", "commit", "heartbeat"):
                action = control_type or "meta"
            elif control_type in ("wake_hit", "wake", "wake_trigger"):
                wake_ok, wake_action = self._dispatch_wake_hit(fields, source_lane=source_lane)
                action = wake_action
                if not wake_ok:
                    self._count_state(
                        control_type=control_type or "unknown",
                        source_lane=source_lane,
                        latency_ms=latency_ms,
                        action=action,
                    )
                    return {"ok": False, "error": action, "action": action, "control_type": control_type or "unknown"}
            else:
                action = "unknown_type"
            if capture_fx_updated:
                action = f"{action}+capture_fx"
            self._count_state(
                control_type=control_type or "unknown",
                source_lane=source_lane,
                latency_ms=latency_ms,
                action=action,
            )
        except Exception as e:
            self._count_error()
            util.log(2, f"[transport][control_apply] failed type={control_type} error={str(e)}")
            return {"ok": False, "error": str(e), "action": "error", "control_type": control_type or "unknown"}

        util.log(1, f"[transport][control_apply] type={control_type or 'unknown'} lane={source_lane} action={action}")
        return {"ok": True, "action": action, "control_type": control_type or "unknown"}

    def snapshot(self):
        with self._state_lock:
            state = deepcopy(self._state)
        state["device_aec_available"] = bool(self._device_aec_available)
        state["device_ns_available"] = bool(self._device_ns_available)
        state["device_agc_available"] = bool(self._device_agc_available)
        return state


_COORDINATOR = None
_COORDINATOR_LOCK = threading.Lock()


def get_transport_control_coordinator() -> TransportControlCoordinator:
    global _COORDINATOR
    if _COORDINATOR is not None:
        return _COORDINATOR
    with _COORDINATOR_LOCK:
        if _COORDINATOR is None:
            _COORDINATOR = TransportControlCoordinator()
    return _COORDINATOR
