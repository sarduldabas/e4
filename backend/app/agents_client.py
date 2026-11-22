"""HTTP client for the agents service. The backend never runs agent logic itself."""
from __future__ import annotations

import httpx


class AgentsUnavailable(Exception):
    """The agents service did not answer in time or is down."""


class AgentsError(Exception):
    """The agents service answered with an error."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status = status
        self.detail = detail


class AgentsClient:
    def __init__(self, base_url: str, timeout: float = 8.0, transport: httpx.AsyncBaseTransport | None = None):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kw) -> dict | list:
        try:
            r = await self._client.request(method, path, **kw)
        except (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError) as e:
            raise AgentsUnavailable(str(e) or e.__class__.__name__) from e
        if r.status_code >= 400:
            raise AgentsError(r.status_code, r.text[:500])
        return r.json()

    async def assess_brief(self, payload: dict) -> dict:
        return await self._request("POST", "/v1/brief/assess", json=payload)  # type: ignore[return-value]

    async def list_agents(self) -> list:
        return await self._request("GET", "/v1/agents")  # type: ignore[return-value]

    async def health(self) -> bool:
        try:
            await self._request("GET", "/health")
            return True
        except (AgentsUnavailable, AgentsError):
            return False
