import ast
from pathlib import Path


def _load_tree() -> ast.AST:
    src = Path("core/sisi_booter.py").read_text(encoding="utf-8-sig")
    return ast.parse(src)


def _find_top_level_function(tree: ast.AST, name: str) -> ast.FunctionDef:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"top-level function {name} not found")


def _find_method(tree: ast.AST, class_name: str, method_name: str) -> ast.FunctionDef:
    for node in getattr(tree, "body", []):
        if not isinstance(node, ast.ClassDef) or node.name != class_name:
            continue
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name == method_name:
                return item
    raise AssertionError(f"{class_name}.{method_name} not found")


def test_accept_audio_device_output_connect_starts_listener():
    tree = _load_tree()
    fn = _find_top_level_function(tree, "accept_audio_device_output_connect")

    start_call_found = False
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        if not isinstance(node.func, ast.Attribute):
            continue
        if node.func.attr != "start":
            continue
        if isinstance(node.func.value, ast.Name) and node.func.value.id == "deviceInputListener":
            start_call_found = True
            break

    assert start_call_found, (
        "accept_audio_device_output_connect() must call deviceInputListener.start() "
        "so remote ASR loop is actually started."
    )


def test_device_input_listener_get_stream_waits_for_stream_cache():
    tree = _load_tree()
    method = _find_method(tree, "DeviceInputListener", "get_stream")

    while_tests = []
    for node in ast.walk(method):
        if isinstance(node, ast.While):
            while_tests.append(ast.unparse(node.test))

    assert any(
        ("self.deviceConnector" in expr and "self.streamCache" in expr)
        for expr in while_tests
    ), (
        "DeviceInputListener.get_stream() must wait for both deviceConnector and "
        "streamCache readiness to avoid returning None and idling forever."
    )


def test_transport_interrupt_apply_is_output_only_not_global_stop():
    tree = _load_tree()
    method = _find_method(tree, "DeviceInputListener", "_dispatch_interrupt_apply_async")

    called_attrs = [
        node.func.attr
        for node in ast.walk(method)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    ]

    assert "stop_music" in called_attrs, (
        "transport interrupt apply path should stop output queues only (stop_music), "
        "instead of killing whole assistant subsystems."
    )
    assert "stop_all_activities" not in called_attrs, (
        "transport interrupt apply path must not call stop_all_activities() because "
        "barge-in should preempt output, not global-stop Agent/LLM."
    )
