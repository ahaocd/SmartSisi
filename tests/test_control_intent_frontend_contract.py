from pathlib import Path


def test_ws_bridge_emits_control_intent_custom_event():
    src = Path("gui/frontend/src/api/wsBridge.js").read_text(encoding="utf-8")
    assert 'const controlIntent = obj.control_intent || obj.controlIntent;' in src
    assert 'window.dispatchEvent(new CustomEvent("smartsisi:control-intent"' in src
    assert "emitControlIntentEvent(payload);" in src


def test_chat_composer_executes_whitelisted_control_actions():
    src = Path("gui/frontend/src/components/ChatComposer.vue").read_text(encoding="utf-8")
    assert "const CONTROL_ACTION_WHITELIST = new Set([" in src
    assert '"open_multimodal"' in src
    assert '"capture_frames_and_analyze"' in src
    assert '"video_call_start"' in src
    assert "window.addEventListener(\"smartsisi:control-intent\", onControlIntentEvent);" in src
    assert "await apiV1RealtimeSession(" in src
    assert "await apiV1RealtimeEvent(" in src
    assert "await captureFramesFromCamera(args);" in src
