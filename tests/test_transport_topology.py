from core import transport_topology as tt


def test_load_transport_topology_defaults(monkeypatch):
    monkeypatch.setattr(tt.config_util, "get_value", lambda key, default=None: default, raising=False)

    topology = tt.load_transport_topology()

    assert topology.device_tcp_port == 9001
    assert topology.device_ws_port == 9002
    assert topology.device_tcp_target_port == 10001
    assert topology.control_lane_enabled is True
    assert topology.control_lane_required is True
    assert topology.control_tcp_port == 9004
    assert topology.control_ws_port == 9003
    assert topology.health_probe_interval_ms == 5000
    assert topology.gateway_enabled is True
    assert topology.gateway_host == "0.0.0.0"
    assert topology.gateway_port == 9102
    assert topology.resolved_gateway_media_backend() == "ws://127.0.0.1:9002"
    assert topology.resolved_gateway_control_backend() == "ws://127.0.0.1:9003"


def test_load_transport_topology_overrides_and_parse(monkeypatch):
    values = {
        "device_tcp_port": "9101",
        "device_ws_port": "9102",
        "device_tcp_target_port": "11001",
        "control_lane_enabled": "true",
        "control_lane_required": "true",
        "control_tcp_port": "9104",
        "control_ws_port": "9103",
        "transport_health_probe_interval_ms": "2500",
        "gateway_front_door_enabled": "true",
        "gateway_front_door_host": "127.0.0.1",
        "gateway_front_door_port": "9200",
        "gateway_media_backend": "ws://127.0.0.1:9102",
        "gateway_control_backend": "ws://127.0.0.1:9103",
        "gateway_access_token": "token-x",
        "gateway_max_message_bytes": "4096",
    }
    monkeypatch.setattr(tt.config_util, "get_value", lambda key, default=None: values.get(key, default), raising=False)

    topology = tt.load_transport_topology()

    assert topology.device_tcp_port == 9101
    assert topology.device_ws_port == 9102
    assert topology.device_tcp_target_port == 11001
    assert topology.control_lane_enabled is True
    assert topology.control_lane_required is True
    assert topology.control_tcp_port == 9104
    assert topology.control_ws_port == 9103
    assert topology.health_probe_interval_ms == 2500
    assert topology.gateway_enabled is True
    assert topology.gateway_host == "127.0.0.1"
    assert topology.gateway_port == 9200
    assert topology.gateway_access_token == "token-x"
    assert topology.gateway_max_message_bytes == 4096
    assert topology.resolved_gateway_media_backend() == "ws://127.0.0.1:9102"
    assert topology.resolved_gateway_control_backend() == "ws://127.0.0.1:9103"
