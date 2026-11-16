"""Prevent a Windows pytest collection failure from old Starlette startup APIs."""
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
import api

ROOT = Path(__file__).resolve().parents[1]


def test_api_imports_when_legacy_add_event_handler_is_missing():
    """A supported FastAPI/Starlette stack need not expose the old method."""
    command = (
        "from starlette.applications import Starlette\n"
        "if hasattr(Starlette, 'add_event_handler'):\n"
        "    delattr(Starlette, 'add_event_handler')\n"
        "import api\n"
        "assert callable(api.app.router.lifespan_context)\n"
    )
    completed = subprocess.run(
        [sys.executable, '-c', command], cwd=ROOT, capture_output=True,
        text=True, encoding='utf-8', errors='replace', timeout=40,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_index_restart_remains_attached_to_fastapi_startup(monkeypatch):
    """The modernization must not just suppress startup indexing."""
    calls = []
    monkeypatch.setattr(api, 'restart_consented_file_index', lambda: calls.append('startup'))
    with TestClient(api.app):
        assert calls == ['startup']
    assert calls == ['startup']
