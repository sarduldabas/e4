from fastapi import APIRouter, HTTPException, Request

from ..agents_client import AgentsError, AgentsUnavailable

router = APIRouter(tags=["system"])


@router.get("/health")
async def health(request: Request) -> dict:
    agents_ok = await request.app.state.agents.health()
    return {"status": "ok", "service": "backend", "agents": "up" if agents_ok else "down"}


@router.get("/api/v1/agents", summary="Agents known to the solution and whether the agents service is reachable")
async def agents(request: Request) -> list:
    try:
        return await request.app.state.agents.list_agents()
    except AgentsUnavailable as e:
        raise HTTPException(503, f"Agents service not reachable: {e}") from e
    except AgentsError as e:
        raise HTTPException(502, f"Agents service error ({e.status})") from e
