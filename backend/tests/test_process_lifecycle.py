"""Regression tests for isolated web and background process lifecycles."""
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _module(path):
    return ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))


def test_web_module_does_not_own_or_start_background_jobs():
    tree = _module("main.py")
    names = {
        node.id for node in ast.walk(tree)
        if isinstance(node, ast.Name)
    }
    imports = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "backend.background_jobs"
    ]
    assert "start_background_jobs" not in names
    assert not imports


def test_only_one_ip_blocking_request_guard_is_registered():
    source = (ROOT / "main.py").read_text(encoding="utf-8-sig")
    assert source.count("def enforce_platform_ip_blocks") == 1
    assert "backend.security.ip_guard" not in source
    assert "from backend.security_ip_guard import client_ip_from_request, ip_is_blocked" in source


def test_worker_starts_jobs_without_importing_flask_application():
    tree = _module("backend/background_worker.py")
    imports_main = [
        node for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        and (
            (isinstance(node, ast.Import) and any(alias.name == "main" for alias in node.names))
            or (isinstance(node, ast.ImportFrom) and node.module == "main")
        )
    ]
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "start_background_jobs"
    ]
    assert not imports_main
    assert len(calls) == 1


def test_background_jobs_retry_failed_daily_runs():
    tree = _module("backend/background_jobs.py")
    source = (ROOT / "backend/background_jobs.py").read_text(encoding="utf-8")
    assert "last_successful_run_date = today" in source
    assert "if succeeded:" in source
    assert "it will be retried" in source


def test_render_uses_gunicorn_and_separate_background_worker():
    render = (ROOT / "render.yaml").read_text(encoding="utf-8")
    assert "startCommand: gunicorn --config gunicorn.conf.py main:app" in render
    assert "startCommand: python -m backend.background_worker" in render
    worker_section = render.split("name: revelacode-background-worker", 1)[1].split(
        "- type: cron", 1
    )[0]
    assert "key: MONGO_URI" in worker_section
