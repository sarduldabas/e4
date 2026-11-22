import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents_client import AgentsClient
from app.config import Settings
from app.main import create_app

ASSESSMENT = {
    "agent": {"name": "brief", "version": "0.1.0", "mode": "rules"}, "lang": "en",
    "strength": {"score": 42, "label_key": "good_basis", "label": "Good basis", "summary": "x y.", "hints": ["a"],
                 "missing": ["topic"], "breakdown": [{"key": "topic", "label": "Topic", "points": 0, "max": 15}]},
    "understood": {"topic": None, "committee": "FAKOM", "date": None},
    "questions": [{"id": "q1", "text": "Q?", "options": [{"id": "a", "label": "A"}], "answer": None}],
    "already_clear": [], "can_start": False,
}


def make_client(tmp_path, handler):
    agents = AgentsClient("http://agents.test", transport=httpx.MockTransport(handler))
    app = create_app(Settings(data_dir=tmp_path), agents=agents)
    return TestClient(app)


def agents_ok(request: httpx.Request):
    if request.url.path == "/v1/brief/assess":
        return httpx.Response(200, json=ASSESSMENT)
    if request.url.path == "/health":
        return httpx.Response(200, json={"status": "ok"})
    if request.url.path == "/v1/agents":
        return httpx.Response(200, json=[{"id": "brief", "status": "available"}])
    return httpx.Response(404)


def agents_down(request: httpx.Request):
    raise httpx.ConnectError("refused")


def test_brief_assess_forwards_and_validates(tmp_path):
    seen = {}

    def handler(request):
        seen["body"] = request.read()
        return agents_ok(request)

    with make_client(tmp_path, handler) as c:
        r = c.post("/api/v1/brief/assess", json={"lang": "en", "text": "hello", "answers": {"q1": "approve"}})
    assert r.status_code == 200
    assert r.json()["strength"]["score"] == 42
    assert b'"answers":{"q1":"approve"}' in seen["body"].replace(b" ", b"")


def test_brief_assess_503_when_agents_down(tmp_path):
    with make_client(tmp_path, agents_down) as c:
        r = c.post("/api/v1/brief/assess", json={"text": "x"})
        assert r.status_code == 503
        assert c.get("/health").json() == {"status": "ok", "service": "backend", "agents": "down"}


def test_brief_assess_rejects_bad_input(tmp_path):
    with make_client(tmp_path, agents_ok) as c:
        assert c.post("/api/v1/brief/assess", json={"lang": "fr"}).status_code == 422


def test_agents_error_is_502(tmp_path):
    with make_client(tmp_path, lambda r: httpx.Response(500, text="boom")) as c:
        assert c.post("/api/v1/brief/assess", json={}).status_code == 502


def test_health_and_agents_list(tmp_path):
    with make_client(tmp_path, agents_ok) as c:
        assert c.get("/health").json()["agents"] == "up"
        assert c.get("/api/v1/agents").json()[0]["id"] == "brief"


def test_committees_and_reports_crud(tmp_path):
    with make_client(tmp_path, agents_ok) as c:
        assert [x["id"] for x in c.get("/api/v1/committees").json()] == ["fakom", "tsc", "ic"]
        assert len(c.get("/api/v1/reports").json()) == 3
        created = c.post("/api/v1/reports", json={"title": "Test", "committee_id": "tsc"})
        assert created.status_code == 201
        rid = created.json()["id"]
        assert created.json()["committee"] == "Technical Steering Committee"
        saved = c.put(f"/api/v1/reports/{rid}/workspace", json={"brief": {"text": "hi"}})
        assert saved.status_code == 200 and saved.json()["workspace"]["brief"]["text"] == "hi"
        assert c.get(f"/api/v1/reports/{rid}").json()["workspace"]["brief"]["text"] == "hi"
        assert all("workspace" not in r for r in c.get("/api/v1/reports").json())
        assert c.delete(f"/api/v1/reports/{rid}").status_code == 204
        assert c.get(f"/api/v1/reports/{rid}").status_code == 404
        assert c.post("/api/v1/reports", json={"committee_id": "nope"}).status_code == 422


def test_cors_allows_dev_origin(tmp_path):
    with make_client(tmp_path, agents_ok) as c:
        r = c.options("/api/v1/brief/assess", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "POST"})
        assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"
