"""Agent 3: source-planner. Decides where to look for each section."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .util import clip, tokens

Lang = Literal["de", "en"]
Kind = Literal["files", "sharepoint", "mail", "teams", "sap", "web"]


class PlanSection(BaseModel):
    key: str
    title: str
    purpose: str = ""
    required_inputs: list[str] = Field(default_factory=list)


class SourcePlannerInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    description: str = ""
    committee: str | None = None
    sections: list[PlanSection] = Field(default_factory=list)
    user_statements: list[str] = Field(default_factory=list)
    available_kinds: list[Kind] = Field(default_factory=lambda: ["files"])
    allow_web: bool = False


class SourceQuery(BaseModel):
    id: str
    kind: Kind
    query: str
    section_keys: list[str] = Field(default_factory=list)
    why: str = ""


class SourcePlannerOutput(BaseModel):
    queries: list[SourceQuery]
    notes: str | None = None


class SourcePlanner(BaseAgent[SourcePlannerInput, SourcePlannerOutput]):
    id = "source-planner"
    name = "Source planner"
    stage = 2
    tier = "standard"
    description = "Plans which sources to search, with which search terms, for which section."
    input_model = SourcePlannerInput
    output_model = SourcePlannerOutput
    system = """
Plan the search for source material for a committee report.
- Produce 1-3 short search queries per section and per useful source kind. A query is 2-6 keywords (the topic's own
  terms, supplier or product names, document types such as "Angebot", "Kostenmodell", "Vorlage", "Protokoll"), not a sentence.
- Only use source kinds listed in "available_kinds". Use "web" only if "allow_web" is true and only for external facts
  (market, suppliers, regulation), never for internal figures.
- "section_keys": the sections the query serves (keys from the request). A query serving the whole report uses all keys.
- "why": one short phrase. Ids: "q1", "q2", ...
- Put anything you could not plan for in "notes"."""

    def rules(self, inp: SourcePlannerInput) -> SourcePlannerOutput:
        base = [w for w in tokens(inp.topic)][:4]
        queries: list[SourceQuery] = []
        n = 0

        def add(kind: str, q: str, keys: list[str], why: str):
            nonlocal n
            n += 1
            queries.append(SourceQuery(id=f"q{n}", kind=kind, query=clip(q, 80), section_keys=keys, why=why))

        topic_q = " ".join(inp.topic.split()[:6]) or " ".join(base)
        kinds = [k for k in inp.available_kinds if k != "web" or inp.allow_web]
        for k in kinds:
            if k != "web":
                add(k, topic_q, [s.key for s in inp.sections], "Thema insgesamt" if inp.lang == "de" else "whole topic")
        for s in inp.sections:
            terms = " ".join(sorted(tokens(s.title))[:3])
            for k in kinds:
                add(k, f"{topic_q} {terms}".strip() if k != "web" else f"{topic_q} {terms}", [s.key], s.title)
        return SourcePlannerOutput(queries=queries[:40])

    def clean(self, inp: SourcePlannerInput, out: SourcePlannerOutput) -> SourcePlannerOutput:
        keys = {s.key for s in inp.sections}
        allowed = {k for k in inp.available_kinds if k != "web" or inp.allow_web}
        good, seen = [], set()
        for q in out.queries:
            if q.kind not in allowed or not q.query.strip():
                continue
            sig = (q.kind, q.query.lower().strip())
            if sig in seen:
                continue
            seen.add(sig)
            good.append(q.model_copy(update={"id": f"q{len(good) + 1}", "query": clip(q.query, 80), "section_keys": [k for k in q.section_keys if k in keys] or sorted(keys)}))
        return out.model_copy(update={"queries": good[:40]})
