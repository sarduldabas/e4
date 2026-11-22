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


class AgentsRunner:
    """Synchronous. Stateless agents: the payload is the only thing they get."""

    def __init__(self, base_url: str, timeout: float, db: Database, transport: httpx.BaseTransport | None = None):
        self._c = httpx.Client(base_url=base_url, timeout=timeout, transport=transport)
        self._db = db

    def close(self) -> None:
        self._c.close()

    def run(self, agent_id: str, payload: dict, *, report_id: str | None = None, job_id: str | None = None) -> dict:
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
                           usage=(env or {}).get("usage") or {}, input=payload, output=(env or {}).get("output")))
        if env is None:
            raise AgentCallFailed(agent_id, err or "unknown error", unreachable)
        return env["output"]
