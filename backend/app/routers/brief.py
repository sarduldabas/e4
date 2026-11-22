from fastapi import APIRouter, HTTPException, Request

from ..agents_client import AgentsError, AgentsUnavailable
from ..schemas import BriefAssessment, BriefAssessRequest

router = APIRouter(prefix="/api/v1/brief", tags=["brief"])


@router.post("/assess", response_model=BriefAssessment,
             summary="Score the brief, list what is missing and return the optional quick questions (Brief agent)")
async def assess(req: BriefAssessRequest, request: Request) -> BriefAssessment:
    client = request.app.state.agents
    try:
        data = await client.assess_brief(req.model_dump())
    except AgentsUnavailable as e:
        raise HTTPException(503, f"Agents service not reachable: {e}") from e
    except AgentsError as e:
        raise HTTPException(502, f"Agents service error ({e.status}): {e.detail}") from e
    return BriefAssessment.model_validate(data)
