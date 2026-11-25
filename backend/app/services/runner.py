"""Calls the agents service and writes every call to the audit trail (agent_runs)."""
from __future__ import annotations

import time

import httpx

from ..db import Database
from ..models import AgentRun


class AgentCallFailed(Exception):
    def __init__(self, agent_id: str, message: str, unreachable: bool = False):
        super().__init__(f"{agent_id}: {message}")
        self.agent_id, self.unreachable = agent_id, unreachable


def shrink(x, limit: int = 3000, depth: int = 0):
    """What the audit trail keeps of a payload: pictures become a size note and long texts are cut, so the trail stays readable and small."""
    if isinstance(x, str):
        if x.startswith("data:image"):
            return f"[Bild, {len(x) // 1365} KB]"
        return x if len(x) <= limit else x[:limit] + f" …[+{len(x) - limit} Zeichen]"
    if isinstance(x, list):
        out = [shrink(i, limit, depth + 1) for i in x[:80]]
        return out + [f"…[+{len(x) - 80} Einträge]"] if len(x) > 80 else out
    if isinstance(x, dict):
        return {k: shrink(v, limit, depth + 1) for k, v in x.items()}
    return x


class AgentsRunner:
    """Synchronous. Stateless agents: the payload is the only thing they get."""

    def __init__(self, base_url: str, timeout: float, db: Database, transport: httpx.BaseTransport | None = None):
        self._c = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._db = db

    def close(self) -> None:
        self._c.close()

    def run(self, agent_id: str, payload: dict, *, report_id: str | None = None, job_id: str | None = None) -> dict:
        return self.run_env(agent_id, payload, report_id=report_id, job_id=job_id)["output"]

    def run_env(self, agent_id: str, payload: dict, *, report_id: str | None = None, job_id: str | None = None) -> dict:
        """Like run(), but returns the whole answer: output plus mode (llm | rules), model, note and token usage."""
        started = time.perf_counter()
        env: dict | None = None
        err: str | None = None
        unreachable = False
        try:
            r = self._c.post(f"/v1/agents/{agent_id}/run", json=payload)
            if r.status_code >= 400:
                err = f"HTTP {r.status_code}: {r.text[:300]}"
            else:
                env = r.json()
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
            err, unreachable = f"agents service not reachable: {str(e) or e.__class__.__name__}", True
        ms = round((time.perf_counter() - started) * 1000)
        with self._db.session() as s:
            s.add(AgentRun(report_id=report_id, job_id=job_id, agent_id=agent_id, mode=(env or {}).get("mode"), model=(env or {}).get("model"),
                           status="ok" if env else "error", error=err, note=(env or {}).get("note"), duration_ms=(env or {}).get("duration_ms") or ms,
                           usage=(env or {}).get("usage") or {}, input=shrink(payload), output=shrink((env or {}).get("output"))))
        if env is None:
            raise AgentCallFailed(agent_id, err or "unknown error", unreachable)
        return env
