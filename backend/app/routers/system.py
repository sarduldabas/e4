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


@router.get("/api/v1/slide-layouts", summary="Slide layouts (slots on a 1280x720 canvas) and the default theme: what the page needs to draw a slide")
def slide_layouts() -> dict:
    from ..core.slides import layouts
    from ..core.slides.spec import default_theme
    return {**layouts(), "theme": default_theme()}


@router.get("/api/v1/system/status", summary="What the page needs to decide between demo and live: is the agents service up, and does it use a language model?")
async def system_status(request: Request) -> dict:
    info = await request.app.state.agents.info()
    settings = request.app.state.ctx.settings
    llm = (info or {}).get("llm") or {}
    return {"backend": "ok", "agents": "up" if info else "down", "mode": (info or {}).get("mode"), "llm": {"configured": bool(llm.get("configured")), "deployment": llm.get("deployment"), "auth": llm.get("auth")},
            "web_enabled": settings.allow_web}
