"""Process lifecycle regression tests; no database connection is required."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _module(path):
    return ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))


def test_web_module_does_not_start_background_jobs_at_import_time():
    tree = _module("main.py")
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "start_background_jobs"
    ]
    assert len(calls) == 1
    call = calls[0]
    assert isinstance(call, ast.Expr)
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    assert isinstance(parents[call], ast.FunctionDef)
    assert parents[call].name == "main"


def test_dedicated_worker_starts_background_jobs():
    tree = _module("backend/background_worker.py")
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "start_background_jobs"
    ]
    assert len(calls) == 1


def test_render_uses_gunicorn_and_separate_background_worker():
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "startCommand: gunicorn --config gunicorn.conf.py main:app" in render
    assert "startCommand: python -m backend.background_worker" in render
