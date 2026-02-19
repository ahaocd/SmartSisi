from pathlib import Path


def test_flask_server_has_transport_status_route():
    src = Path("gui/flask_server.py").read_text(encoding="utf-8")
    assert "@__app.route('/api/v1/transport/status', methods=['get'])" in src
    assert "sisi_booter.get_transport_runtime_status()" in src
