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
    data_url: str | None = None  # small preview (data:image/png;base64,...) for images; used by the vision model only


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
    tier = "vision"
    description = "Picks the images and tables from the sources that fit a section, with a caption."
    input_model = AssetCuratorInput
    output_model = AssetCuratorOutput
    system = """
You choose visual material for the slides: images, tables and charts found in the sources.
For each candidate decide: does it help a section tell its story to a committee? Choose at most "max_per_section" per section.
Reject logos, decorative pictures, screenshots of menus, unreadable or low-resolution items (below 300 px wide) and anything
that duplicates another choice. Give each choice a "caption" (short, factual, in the report language), a "score" 0..1 and a
short "reason". Attached preview images are the actual pictures: look at them. Put all other candidate ids in "rejected"."""

    def images(self, inp: AssetCuratorInput) -> list[str]:
        return [c.data_url for c in inp.candidates if c.data_url][:8]

    def _image_fields(self) -> set[str]:
        return set()

    def user_message(self, inp: AssetCuratorInput) -> str:
        slim = inp.model_copy(update={"candidates": [c.model_copy(update={"data_url": None}) for c in inp.candidates]})
        return slim.model_dump_json(exclude_none=True)

    def rules(self, inp: AssetCuratorInput) -> AssetCuratorOutput:
        sec = {s.key: tokens(s.title + " " + s.purpose) for s in inp.sections}
        chosen: list[AssetChoice] = []
        taken: dict[str, int] = {}
        rejected = []
        scored = []
        for c in inp.candidates:
            small = c.kind == "image" and c.width is not None and c.width < 300
            t = tokens(c.caption + " " + c.context)
            key, sc = max(((k, overlap(v, t)) for k, v in sec.items()), key=lambda kv: kv[1], default=(None, 0.0))
            if small or not key or sc < 0.15:
                rejected.append(c.id)
                continue
            scored.append((sc + (0.1 if c.kind == "table" else 0), key, c))
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
