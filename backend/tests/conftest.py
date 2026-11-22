import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

AGENTS_DIR = Path(__file__).resolve().parents[2] / "agents"


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def agents_url():
    """The real agents service (rules mode) in a subprocess: the two services never import each other."""
    if not AGENTS_DIR.exists():
        pytest.skip("agents/ folder not next to backend/")
    port = _free_port()
    p = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port), "--log-level", "warning"], cwd=AGENTS_DIR,
                         env={**os.environ, "AGENT_MODE": "rules"})
    url = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(url + "/health", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.2)
    else:
        p.kill()
        raise RuntimeError("agents service did not start")
    yield url
    p.terminate()
    p.wait(5)


@pytest.fixture()
def make_client(tmp_path, agents_url):
    from app.config import Settings
    from app.main import create_app
    opened = []

    def _make(url: str | None = None, **settings):
        app = create_app(Settings(data_dir=tmp_path / "data", agents_url=url or agents_url, **settings), inline_jobs=True)
        c = TestClient(app)
        c.__enter__()
        opened.append(c)
        return c

    yield _make
    for c in opened:
        c.__exit__(None, None, None)
