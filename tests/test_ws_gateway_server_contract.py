import pytest

from gateway.app.ws_gateway_server import WsGatewayServer


def test_ws_gateway_requires_explicit_control_backend():
    with pytest.raises(ValueError):
        WsGatewayServer(
            host="127.0.0.1",
            port=9102,
            media_backend_url="ws://127.0.0.1:9002",
            control_backend_url="",
        )

