import ast
from pathlib import Path


def _find_question_function(tree: ast.AST) -> ast.FunctionDef:
    for node in getattr(tree, "body", []):
        if isinstance(node, ast.FunctionDef) and node.name == "question":
            return node
    raise AssertionError("question() not found in llm/liusisi.py")


def test_question_does_not_shadow_get_current_system_mode():
    src = Path("llm/liusisi.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    question_fn = _find_question_function(tree)

    shadow_import_lines = []
    for node in ast.walk(question_fn):
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.module != "llm.liusisi":
            continue
        if any(alias.name == "get_current_system_mode" for alias in node.names):
            shadow_import_lines.append(node.lineno)

    assert not shadow_import_lines, (
        "question() must not import get_current_system_mode from llm.liusisi; "
        f"found local imports at lines: {shadow_import_lines}"
    )
