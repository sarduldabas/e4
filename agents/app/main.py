"""Agents service. One HTTP endpoint per agent; the backend is the only caller."""
from __future__ import annotations

import os

from fastapi import FastAPI

from .agents.brief_agent import BriefAgent
from .schemas import BriefAssessment, BriefAssessRequest

app = FastAPI(title="COE4 Agents", version="0.1.0", description="Agents behind the Committee Report Assistant.")

brief_agent = BriefAgent()

# Registry shown by the backend. Planned agents are listed so the roadmap is visible; they have no endpoint yet.
AGENTS = [
    {"id": "brief", "stage": 1, "name": "Brief agent", "status": "available", "endpoint": "/v1/brief/assess",
     "description": brief_agent.description, "version": brief_agent.version},
    {"id": "reader", "stage": 2, "name": "Reader", "status": "planned", "description": "Reads files, mails and chats."},
    {"id": "extractor", "stage": 2, "name": "Extractor", "status": "planned", "description": "Extracts figures, tables and images."},
    {"id": "researcher", "stage": 2, "name": "Researcher", "status": "planned", "description": "Searches Confluence, Jira, Wiki and the web."},
    {"id": "analyst", "stage": 2, "name": "Analyst", "status": "planned", "description": "Compares options and builds charts."},
    {"id": "cross-checker", "stage": 2, "name": "Cross-checker", "status": "planned", "description": "Checks every figure and flags conflicts."},
    {"id": "challenger", "stage": 2, "name": "Challenger", "status": "planned", "description": "Predicts the committee's questions."},
    {"id": "slide-builder", "stage": 3, "name": "Slide builder", "status": "planned", "description": "Maps the analysis to the committee template."},
]


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "agents", "agents_available": [a["id"] for a in AGENTS if a["status"] == "available"],
            "mode": os.environ.get("AGENT_MODE", "rules")}


@app.get("/v1/agents")
def list_agents() -> list[dict]:
    return AGENTS


@app.post("/v1/brief/assess", response_model=BriefAssessment)
def assess_brief(req: BriefAssessRequest) -> BriefAssessment:
    return brief_agent.assess(req)
