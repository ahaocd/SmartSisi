from __future__ import annotations

from dataclasses import dataclass
from typing import Dict

from utils import config_util


DEFAULT_DEVICE_TCP_PORT = 9001
DEFAULT_DEVICE_WS_PORT = 9002
DEFAULT_DEVICE_TCP_TARGET_PORT = 10001
DEFAULT_CONTROL_WS_PORT = 9003
DEFAULT_CONTROL_TCP_PORT = 9004
DEFAULT_GATEWAY_HOST = "0.0.0.0"
DEFAULT_GATEWAY_PORT = 9102
DEFAULT_GATEWAY_MAX_MESSAGE_BYTES = 2 * 1024 * 1024
DEFAULT_HEALTH_PROBE_INTERVAL_MS = 5000


def _to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value or "").strip().lower()
    return text in {"1", "true", "yes", "on"}


def _to_int(value, default: int) -> int:
    try:
        return int(str(value).strip())
    except Exception:
        return int(default)


def _to_text(value, default: str = "") -> str:
    text = str(value if value is not None else "").strip()
    return text or default


@dataclass(frozen=True)
class TransportTopology:
    device_tcp_port: int
    device_ws_port: int
    device_tcp_target_port: int
    control_lane_enabled: bool
    control_lane_required: bool
    control_tcp_port: int
    control_ws_port: int
    health_probe_interval_ms: int
    gateway_enabled: bool
    gateway_host: str
    gateway_port: int
    gateway_media_backend: str
    gateway_control_backend: str
    gateway_access_token: str
    gateway_max_message_bytes: int

    def resolved_gateway_media_backend(self) -> str:
        if self.gateway_media_backend:
            return self.gateway_media_backend
        return f"ws://127.0.0.1:{self.device_ws_port}"

    def resolved_control_ws_backend(self) -> str:
        return f"ws://127.0.0.1:{self.control_ws_port}"

    def resolved_gateway_control_backend(self) -> str:
        if self.gateway_control_backend:
            return self.gateway_control_backend
        return self.resolved_control_ws_backend()

    def summary_fields(self) -> Dict[str, str]:
        return {
            "tcp_port": str(self.device_tcp_port),
            "ws_port": str(self.device_ws_port),
            "target_tcp": str(self.device_tcp_target_port),
            "control_lane_enabled": str(self.control_lane_enabled),
            "control_lane_required": str(self.control_lane_required),
            "control_tcp_port": str(self.control_tcp_port),
            "control_ws_port": str(self.control_ws_port),
            "health_probe_interval_ms": str(self.health_probe_interval_ms),
            "gateway_enabled": str(self.gateway_enabled),
            "gateway_host": self.gateway_host,
            "gateway_port": str(self.gateway_port),
            "gateway_media_backend": self.resolved_gateway_media_backend(),
            "gateway_control_backend": self.resolved_gateway_control_backend(),
        }


def load_transport_topology() -> TransportTopology:
    tcp_port = _to_int(
        config_util.get_value("device_tcp_port", DEFAULT_DEVICE_TCP_PORT),
        DEFAULT_DEVICE_TCP_PORT,
    )
    ws_port = _to_int(
        config_util.get_value("device_ws_port", DEFAULT_DEVICE_WS_PORT),
        DEFAULT_DEVICE_WS_PORT,
    )
    target_tcp_port = _to_int(
        config_util.get_value("device_tcp_target_port", DEFAULT_DEVICE_TCP_TARGET_PORT),
        DEFAULT_DEVICE_TCP_TARGET_PORT,
    )
    control_lane_enabled = _to_bool(config_util.get_value("control_lane_enabled", True))
    control_lane_required = _to_bool(config_util.get_value("control_lane_required", True))
    control_tcp_port = _to_int(
        config_util.get_value("control_tcp_port", DEFAULT_CONTROL_TCP_PORT),
        DEFAULT_CONTROL_TCP_PORT,
    )
    control_ws_port = _to_int(
        config_util.get_value("control_ws_port", DEFAULT_CONTROL_WS_PORT),
        DEFAULT_CONTROL_WS_PORT,
    )
    health_probe_interval_ms = _to_int(
        config_util.get_value("transport_health_probe_interval_ms", DEFAULT_HEALTH_PROBE_INTERVAL_MS),
        DEFAULT_HEALTH_PROBE_INTERVAL_MS,
    )

    gateway_enabled = _to_bool(config_util.get_value("gateway_front_door_enabled", True))
    gateway_host = _to_text(
        config_util.get_value("gateway_front_door_host", DEFAULT_GATEWAY_HOST),
        DEFAULT_GATEWAY_HOST,
    )
    gateway_port = _to_int(
        config_util.get_value("gateway_front_door_port", DEFAULT_GATEWAY_PORT),
        DEFAULT_GATEWAY_PORT,
    )
    gateway_media_backend = _to_text(config_util.get_value("gateway_media_backend", ""), "")
    gateway_control_backend = _to_text(config_util.get_value("gateway_control_backend", ""), "")
    gateway_access_token = _to_text(config_util.get_value("gateway_access_token", ""), "")
    gateway_max_message_bytes = _to_int(
        config_util.get_value("gateway_max_message_bytes", DEFAULT_GATEWAY_MAX_MESSAGE_BYTES),
        DEFAULT_GATEWAY_MAX_MESSAGE_BYTES,
    )

    return TransportTopology(
        device_tcp_port=tcp_port,
        device_ws_port=ws_port,
        device_tcp_target_port=target_tcp_port,
        control_lane_enabled=control_lane_enabled,
        control_lane_required=control_lane_required,
        control_tcp_port=control_tcp_port,
        control_ws_port=control_ws_port,
        health_probe_interval_ms=health_probe_interval_ms,
        gateway_enabled=gateway_enabled,
        gateway_host=gateway_host,
        gateway_port=gateway_port,
        gateway_media_backend=gateway_media_backend,
        gateway_control_backend=gateway_control_backend,
        gateway_access_token=gateway_access_token,
        gateway_max_message_bytes=gateway_max_message_bytes,
    )
