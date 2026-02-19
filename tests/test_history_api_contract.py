from pathlib import Path


def _get_api_get_msg_block(src: str) -> str:
    marker = "@__app.route('/api/get-msg', methods=['post'])"
    start = src.find(marker)
    assert start >= 0, "missing /api/get-msg route"
    return src[start:start + 3200]


def test_get_msg_uses_real_history_source_of_truth():
    src = Path("gui/flask_server.py").read_text(encoding="utf-8")
    block = _get_api_get_msg_block(src)

    assert "uid = 0" not in block
    assert "return json.dumps({'list': []})" not in block
    assert "_api_get_msg_load_recent_messages(" in src
    assert "from sisi_memory.chat_history import load_history_settings" in src
    assert '"systems"' in block or "'systems'" in block

