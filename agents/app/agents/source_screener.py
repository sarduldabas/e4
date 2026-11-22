"""Agent 4: source-screener. Judges the search hits and decides what is worth reading."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .source_planner import PlanSection
from .util import clip, overlap, tokens

Lang = Literal["de", "en"]


class Candidate(BaseModel):
    id: str
    title: str
    kind: str = "files"
    path: str | None = None
    modified: str | None = None  # ISO date
    excerpt: str = ""
    size_bytes: int | None = None


class SourceScreenerInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    sections: list[PlanSection] = Field(default_factory=list)
    candidates: list[Candidate] = Field(default_factory=list)
    max_selected: int = 25


class Screening(BaseModel):
    candidate_id: str
    include: bool
    relevance: float = Field(ge=0, le=1)
    section_keys: list[str] = Field(default_factory=list)
    reason: str = ""
    duplicate_of: str | None = None


class SourceScreenerOutput(BaseModel):
    decisions: list[Screening]


class SourceScreener(BaseAgent[SourceScreenerInput, SourceScreenerOutput]):
    id = "source-screener"
    name = "Source screener"
    stage = 2
    tier = "small"
    description = "Rates the search hits for relevance and removes duplicates and outdated versions."
    input_model = SourceScreenerInput
    output_model = SourceScreenerOutput
    system = """
Decide for every candidate document whether it is worth reading for this report.
- "relevance" 0..1 for the report topic (1 = central). include = true when relevance >= 0.35 and it is not a duplicate.
- Mark a duplicate or an older version of another candidate with "duplicate_of" = the id of the better one and include = false.
  Prefer the newer one ("modified"), the final over the draft.
- "section_keys": sections it can help (keys from the request), possibly empty.
- "reason": one short phrase. Judge only by title, path and excerpt. Decide on every candidate id, none missing."""

    def rules(self, inp: SourceScreenerInput) -> SourceScreenerOutput:
        topic = tokens(inp.topic + " " + " ".join(s.title for s in inp.sections))
        sec = {s.key: tokens(s.title + " " + s.purpose + " " + " ".join(s.required_inputs)) for s in inp.sections}
        scored = []
        for c in inp.candidates:
            t = tokens(f"{c.title} {c.path or ''} {c.excerpt}")
            rel = min(1.0, 0.15 + 1.6 * overlap(topic, t))
            keys = [k for k, v in sec.items() if overlap(v, t) >= 0.2]
            scored.append((c, round(rel, 2), keys))
        decisions: dict[str, Screening] = {}
        by_stem: dict[str, tuple[Candidate, float]] = {}
        for c, rel, keys in sorted(scored, key=lambda x: (x[0].modified or "", x[1]), reverse=True):
            stem = " ".join(sorted(tokens(c.title))) or c.id
            if stem in by_stem:
                decisions[c.id] = Screening(candidate_id=c.id, include=False, relevance=rel, section_keys=keys, reason="Duplikat/ältere Version" if inp.lang == "de" else "duplicate / older version", duplicate_of=by_stem[stem][0].id)
                continue
            by_stem[stem] = (c, rel)
            decisions[c.id] = Screening(candidate_id=c.id, include=rel >= 0.35, relevance=rel, section_keys=keys,
                                        reason=("passt zum Thema" if inp.lang == "de" else "matches the topic") if rel >= 0.35 else ("kaum Bezug zum Thema" if inp.lang == "de" else "little relation to the topic"))
        return SourceScreenerOutput(decisions=[decisions[c.id] for c in inp.candidates])

    def clean(self, inp: SourceScreenerInput, out: SourceScreenerOutput) -> SourceScreenerOutput:
        ids = {c.id for c in inp.candidates}
        keys = {s.key for s in inp.sections}
        got = {d.candidate_id: d for d in out.decisions if d.candidate_id in ids}
        fallback = {d.candidate_id: d for d in self.rules(inp).decisions}
        decisions = []
        for c in inp.candidates:
            d = got.get(c.id) or fallback[c.id]
            dup = d.duplicate_of if d.duplicate_of in ids and d.duplicate_of != c.id else None
            decisions.append(d.model_copy(update={"section_keys": [k for k in d.section_keys if k in keys], "duplicate_of": dup,
                                                 "include": d.include and dup is None, "reason": clip(d.reason, 120)}))
        chosen = sorted((d for d in decisions if d.include), key=lambda d: -d.relevance)
        for d in chosen[inp.max_selected:]:
            d.include = False
            d.reason = clip(d.reason + " (Limit erreicht)", 120)
        return SourceScreenerOutput(decisions=decisions)
