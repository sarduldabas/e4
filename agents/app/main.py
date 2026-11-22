"""Agents service. One HTTP endpoint per agent; the backend is the only caller."""
from __future__ import annotations

import logging

from fastapi import Body, FastAPI, HTTPException
from pydantic import ValidationError

from .agents.brief_agent import BriefAgent
from .agents.brief_llm import LlmBriefAgent
from .agents.core import AgentRunner
from .agents.registry import build_registry
from .config import Settings, load_settings
from .llm import AzureOpenAIClient, LlmClient, LlmError
from .schemas import BriefAssessment, BriefAssessRequest

log = logging.getLogger("agents")

def build_brief_agent(settings: Settings, llm: LlmClient | None = None):
    """AGENT_MODE=rules: never call a model. llm: model, rules as safety net. auto: model if configured, else rules."""
    rules = BriefAgent()
    wants_llm = settings.agent_mode == "llm" or (settings.agent_mode == "auto" and settings.llm.configured)
    if not wants_llm:
        return rules, None
    if llm is None:
        if not settings.llm.configured:
            log.warning("AGENT_MODE=llm but the LLM settings are incomplete (see agents/.env.example); using the rules agent.")
            return rules, None
        llm = AzureOpenAIClient(settings.llm)
    return LlmBriefAgent(llm, rules), llm


def create_app(settings: Settings | None = None, llm: LlmClient | None = None) -> FastAPI:
    settings = settings or load_settings()
    brief_agent, llm = build_brief_agent(settings, llm)
    mode = "llm" if isinstance(brief_agent, LlmBriefAgent) else "rules"

    app = FastAPI(title="COE4 Agents", version="0.3.0", description="Agents behind the Committee Report Assistant.")
    registry = build_registry()
    # The 12 pipeline agents share one runner: model when configured (AGENT_MODE auto/llm), rules version otherwise.
    runner = AgentRunner(llm if settings.agent_mode != "rules" else None, settings.agent_mode)
    runner_mode = "llm" if runner.uses_model else "rules"
    agents = [
        {"id": "brief", "stage": 1, "name": "Brief agent", "status": "available", "endpoint": "/v1/brief/assess",
         "description": brief_agent.description, "version": brief_agent.version, "mode": mode},
        *({**a.info(), "mode": runner_mode} for a in registry.values()),
    ]

    @app.get("/health")
    def health() -> dict:
        return {
            "status": "ok", "service": "agents", "agents_available": [a["id"] for a in agents if a["status"] == "available"],
            "mode": mode, "agent_mode_setting": settings.agent_mode,
            "llm": {"configured": settings.llm.configured, "deployment": settings.llm.deployment or None,
                    "auth": "entra" if settings.llm.use_entra_id and not settings.llm.api_key else ("key" if settings.llm.api_key else None)},
        }

    @app.get("/health/llm")
    def health_llm() -> dict:
        """Calls the model once. Use it to check endpoint, deployment name and credentials from agents/.env."""
        if llm is None:
            return {"ok": False, "error": "No model in use (AGENT_MODE=rules, or endpoint, deployment and key are missing in agents/.env)."}
        try:
            ping = getattr(llm, "ping", None)
            result = ping() if ping else {"ok": bool(llm.complete_json("Reply with a JSON object.", 'Return {"ok": true}.'))}
        except LlmError as e:
            return {"ok": False, "deployment": llm.model, "error": str(e)}
        return {**result, "deployment": llm.model}

    @app.get("/v1/agents")
    def list_agents() -> list[dict]:
        return agents

    @app.get("/v1/agents/{agent_id}/schema")
    def agent_schema(agent_id: str) -> dict:
        a = registry.get(agent_id)
        if not a:
            raise HTTPException(404, f"unknown agent '{agent_id}'")
        return {**a.info(), "input": a.input_model.model_json_schema(), "output": a.output_model.model_json_schema()}

    @app.post("/v1/agents/{agent_id}/run")
    def run_agent(agent_id: str, payload: dict = Body(...)) -> dict:
        """JSON in, JSON out. The same envelope for every agent; this is what moves to Foundry later."""
        a = registry.get(agent_id)
        if not a:
            raise HTTPException(404, f"unknown agent '{agent_id}'")
        try:
            inp = a.input_model.model_validate(payload)
        except ValidationError as e:
            raise HTTPException(422, detail=e.errors(include_url=False, include_context=False)) from e
        res = runner.run(a, inp)
        return {"agent": a.id, "version": a.version, "mode": res.mode, "model": res.model, "note": res.note,
                "usage": res.usage, "duration_ms": res.duration_ms, "output": res.output.model_dump(mode="json")}

    @app.post("/v1/brief/assess", response_model=BriefAssessment)
    def assess_brief(req: BriefAssessRequest) -> BriefAssessment:
        return brief_agent.assess(req)

    return app


app = create_app()
