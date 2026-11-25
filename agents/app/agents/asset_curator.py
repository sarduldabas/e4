"""Agent 7: asset-curator. Chooses which images, tables and charts from the sources belong on which slide."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .source_planner import PlanSection
from .util import clip, overlap, tokens

Lang = Literal["de", "en"]


class AssetCandidate(BaseModel):
    id: str
    kind: Literal["image", "table", "chart"]
    caption: str = ""
    context: str = ""  # text around it in the source, or table header and first rows
    source_label: str = ""
    width: int | None = None
    height: int | None = None
    role: str = ""  # from the asset-analyst: chart | diagram | photo | screenshot | table_image | ...
    description: str = ""  # what the asset-analyst saw
    legibility: float | None = None
    treatment: str = ""  # use | redraw | discard (the analyst's advice)
    origin: str = ""  # document | web
    has_data: bool = False  # chart data was read, so the chart can be redrawn natively
    section_hints: list[str] = Field(default_factory=list)


class AssetCuratorInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    sections: list[PlanSection] = Field(default_factory=list)
    candidates: list[AssetCandidate] = Field(default_factory=list)
    max_per_section: int = 2


class AssetChoice(BaseModel):
    asset_id: str
    section_key: str
    score: float = Field(ge=0, le=1)
    caption: str = ""
    reason: str = ""


class AssetCuratorOutput(BaseModel):
    chosen: list[AssetChoice] = Field(default_factory=list)
    rejected: list[str] = Field(default_factory=list)


class AssetCurator(BaseAgent[AssetCuratorInput, AssetCuratorOutput]):
    id = "asset-curator"
    name = "Asset curator"
    stage = 2
    tier = "standard"
    description = "Picks, from the catalogue of all images, charts and tables of the sources, those that fit a section, with a caption. Works on the analyst's descriptions, so every asset is considered."
    input_model = AssetCuratorInput
    output_model = AssetCuratorOutput
    system = """
You choose visual material for the slides from a catalogue of ALL images, charts and tables found in the sources. Each candidate has been
looked at already: "role", "description", "legibility", the analyst's advice "treatment" and "has_data" (the chart's numbers are known and will be redrawn natively).
Decide: does it help a section tell its story to a committee? Choose at most "max_per_section" per section.
Prefer: charts and diagrams that carry the section's message, tables that compare options, photos or screenshots that show the real object.
Reject: treatment "discard", logos, decoration, low legibility (< 0.4), duplicates of one another (keep the clearest), anything unrelated to the topic, and web pictures
whose rights are unclear unless they are the only way to show the subject. Give each choice a "caption" (short, factual, in the report language), a "score" 0..1 and a
short "reason". Put all other candidate ids in "rejected"."""

    def rules(self, inp: AssetCuratorInput) -> AssetCuratorOutput:
        sec = {s.key: tokens(s.title + " " + s.purpose) for s in inp.sections}
        chosen: list[AssetChoice] = []
        taken: dict[str, int] = {}
        rejected = []
        scored = []
        for c in inp.candidates:
            small = c.kind == "image" and c.width is not None and c.width < 300
            t = tokens(c.caption + " " + c.context + " " + c.description)
            key, sc = max(((k, overlap(v, t) + (0.5 if k in c.section_hints else 0.0)) for k, v in sec.items()), key=lambda kv: kv[1], default=(None, 0.0))
            if c.treatment == "discard" or (c.legibility is not None and c.legibility < 0.4) or c.role in ("logo", "decorative"):
                rejected.append(c.id)
                continue
            if small or not key or sc < 0.15:
                rejected.append(c.id)
                continue
            scored.append((sc + (0.1 if c.kind == "table" or c.role in ("chart", "diagram") else 0) - (0.1 if c.origin == "web" else 0), key, c))
        for sc, key, c in sorted(scored, key=lambda x: -x[0]):
            if taken.get(key, 0) >= inp.max_per_section:
                rejected.append(c.id)
                continue
            taken[key] = taken.get(key, 0) + 1
            chosen.append(AssetChoice(asset_id=c.id, section_key=key, score=round(min(1.0, sc + 0.3), 2), caption=clip(c.caption or c.source_label, 100), reason="passt zum Abschnitt" if inp.lang == "de" else "fits the section"))
        return AssetCuratorOutput(chosen=chosen, rejected=rejected)

    def clean(self, inp: AssetCuratorInput, out: AssetCuratorOutput) -> AssetCuratorOutput:
        ids = {c.id for c in inp.candidates}
        keys = {s.key for s in inp.sections}
        per: dict[str, int] = {}
        chosen, used = [], set()
        for ch in sorted(out.chosen, key=lambda c: -c.score):
            if ch.asset_id not in ids or ch.section_key not in keys or ch.asset_id in used or per.get(ch.section_key, 0) >= inp.max_per_section:
                continue
            used.add(ch.asset_id)
            per[ch.section_key] = per.get(ch.section_key, 0) + 1
            chosen.append(ch.model_copy(update={"caption": clip(ch.caption, 100), "reason": clip(ch.reason, 120)}))
        return AssetCuratorOutput(chosen=chosen, rejected=[i for i in ids if i not in used])
