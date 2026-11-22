"""Public API models.

The brief models mirror agents/app/schemas.py (the contract with the agents service).
Services do not import each other: if one side changes, change the other and the tests.
"""
from typing import Any, Literal

from pydantic import BaseModel, Field

Lang = Literal["de", "en"]


# ---- brief assessment (stage 1) ------------------------------------------------------------
class BriefFile(BaseModel):
    name: str
    kind: str | None = None
    status: Literal["reading", "ready"] = "ready"


class BriefOverrides(BaseModel):
    topic: str | None = None
    committee: str | None = None
    date: str | None = None
    audience: str | None = None
    template: str | None = None


class BriefAssessRequest(BaseModel):
    lang: Lang = "de"
    text: str = Field("", max_length=20000)
    overrides: BriefOverrides = Field(default_factory=BriefOverrides)
    preset_committee: str | None = None
    files: list[BriefFile] = Field(default_factory=list, max_length=100)
    links: list[str] = Field(default_factory=list, max_length=100)
    connectors: dict[str, bool] = Field(default_factory=dict)
    answers: dict[str, str | None] = Field(default_factory=dict)


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
    summary: str
    hints: list[str]
    missing: list[str]
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
    already_clear: list[str] = Field(default_factory=list)
    can_start: bool


# ---- committees and reports ------------------------------------------------------------------
class Committee(BaseModel):
    id: str
    name: str
    date: str  # ISO yyyy-mm-dd
    template: str
    has_report: bool = False


class ReportSummary(BaseModel):
    id: str
    title: str
    committee: str
    date: str
    version: str = "v1"
    status: Literal["Draft", "Presented", "Decided"] = "Draft"
    stage: int = 1
    edited: str = ""
    people: list[str] = Field(default_factory=list)


class Report(ReportSummary):
    workspace: dict[str, Any] | None = None  # the front end's brief / analysis / deck state


class ReportCreate(BaseModel):
    title: str = "New committee report"
    committee_id: str | None = None


class ErrorBody(BaseModel):
    detail: str
