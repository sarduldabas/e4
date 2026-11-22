"""Request / response contract of the Brief agent.

The backend forwards the front-end payload 1:1, so this file is also the contract
between backend and agents. Keep it small and stable.
"""
from typing import Literal

from pydantic import BaseModel, Field

Lang = Literal["de", "en"]


class BriefFile(BaseModel):
    name: str
    kind: str | None = None
    status: Literal["reading", "ready"] = "ready"


class BriefOverrides(BaseModel):
    """Values the user typed into the 'What I understood' chips. They win over detection."""

    topic: str | None = None
    committee: str | None = None
    date: str | None = None  # dd.mm.yyyy
    audience: str | None = None
    template: str | None = None


class BriefAssessRequest(BaseModel):
    lang: Lang = "de"
    text: str = ""
    overrides: BriefOverrides = Field(default_factory=BriefOverrides)
    preset_committee: str | None = None  # committee id picked on the home screen
    files: list[BriefFile] = Field(default_factory=list)
    links: list[str] = Field(default_factory=list)
    connectors: dict[str, bool] = Field(default_factory=dict)
    answers: dict[str, str | None] = Field(default_factory=dict)  # question id -> option id


class Understood(BaseModel):
    topic: str | None = None
    committee: str | None = None
    date: str | None = None


class BreakdownItem(BaseModel):
    key: str
    label: str
    points: float
    max: float


class Strength(BaseModel):
    score: int
    label_key: Literal["getting_started", "good_basis", "strong_brief", "excellent_brief"]
    label: str
    summary: str  # 2-3 short sentences for the card
    hints: list[str]  # "what would help most", at most 3
    missing: list[str]  # machine keys of what is still missing, in priority order
    breakdown: list[BreakdownItem]


class Option(BaseModel):
    id: str
    label: str


class Question(BaseModel):
    id: str
    text: str
    options: list[Option]
    answer: str | None = None


class AgentInfo(BaseModel):
    name: str
    version: str
    mode: Literal["rules", "llm"]


class BriefAssessment(BaseModel):
    agent: AgentInfo
    lang: Lang
    strength: Strength
    understood: Understood
    questions: list[Question]
    already_clear: list[str] = Field(default_factory=list)  # questions skipped because the text already answers them
    can_start: bool
