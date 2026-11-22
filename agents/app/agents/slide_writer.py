"""Agent 11: slide-writer. Turns the approved claims of a section into slide content."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .section_analyst import ChartSpec, Claim
from .util import clip, pick

Lang = Literal["de", "en"]


class SlideAsset(BaseModel):
    id: str
    kind: Literal["image", "table", "chart"]
    caption: str = ""


class SlideSection(BaseModel):
    key: str
    title: str
    layout: str | None = None
    suggested_slides: int = 1
    headline: str = ""
    claims: list[Claim] = Field(default_factory=list)  # approved only
    charts: list[ChartSpec] = Field(default_factory=list)
    assets: list[SlideAsset] = Field(default_factory=list)


class SlideWriterInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    committee: str | None = None
    section: SlideSection
    max_bullets: int = 5
    max_words_per_bullet: int = 22
    instruction: str | None = None
    previous_slides: list["SlideDraft"] = Field(default_factory=list)


class Bullet(BaseModel):
    text: str
    claim_ids: list[str] = Field(default_factory=list)


class SlideDraft(BaseModel):
    title: str
    bullets: list[Bullet] = Field(default_factory=list)
    chart_id: str | None = None
    asset_ids: list[str] = Field(default_factory=list)
    notes: str = ""
    layout: str | None = None


SlideWriterInput.model_rebuild()


class SlideWriterOutput(BaseModel):
    slides: list[SlideDraft]


class SlideWriter(BaseAgent[SlideWriterInput, SlideWriterOutput]):
    id = "slide-writer"
    name = "Slide writer"
    stage = 3
    tier = "standard"
    description = "Turns the approved claims of a section into slide titles, bullets and speaker notes."
    input_model = SlideWriterInput
    output_model = SlideWriterOutput
    system = """
Write the slide(s) for ONE section from its approved claims.
- "title": an action title, one sentence stating the message (use the headline, tightened). No more than 14 words.
- "bullets": at most max_bullets, each at most max_words_per_bullet words, each tied to the claim id(s) it comes from.
  Say exactly what the claims say: do not add facts, numbers or claims, and do not change a number or a unit. Shorten, never embellish.
- "chart_id" and "asset_ids": use only ids from the request's charts and assets; put at most one chart and two assets on a slide.
- "notes": 2-3 sentences of speaker notes: what to say beyond the bullets, drawn from the claims only.
- Use "suggested_slides" as a guide for the number of slides; split only when the bullets do not fit.
- "layout": copy section.layout.
If "instruction" is given, apply it to "previous_slides". All text in the report language."""

    def rules(self, inp: SlideWriterInput) -> SlideWriterOutput:
        s = inp.section
        title = clip(s.headline or (s.claims[0].text if s.claims else s.title), 110)
        size = max(1, inp.max_bullets)
        groups = [s.claims[i:i + size] for i in range(0, max(len(s.claims), 1), size)][: max(1, s.suggested_slides)] or [[]]
        slides = []
        for n, g in enumerate(groups):
            bullets = [Bullet(text=_shorten(c.text, inp.max_words_per_bullet), claim_ids=[c.id]) for c in g]
            slides.append(SlideDraft(
                title=title if n == 0 else clip(f"{title} ({n + 1})", 120), bullets=bullets,
                chart_id=s.charts[0].id if n == 0 and s.charts else None,
                asset_ids=[a.id for a in s.assets if a.kind != "chart"][:2] if n == 0 else [],
                notes=" ".join(c.text for c in g[:3]), layout=s.layout))
        return SlideWriterOutput(slides=slides)

    def clean(self, inp: SlideWriterInput, out: SlideWriterOutput) -> SlideWriterOutput:
        s = inp.section
        ok = {c.id for c in s.claims}
        charts = {c.id for c in s.charts}
        assets = {a.id for a in s.assets}
        slides = []
        for sl in out.slides:
            bullets = []
            for b in sl.bullets[: inp.max_bullets]:
                ids = [i for i in b.claim_ids if i in ok]
                if ids and b.text.strip():  # a bullet without an approved claim behind it is dropped
                    bullets.append(b.model_copy(update={"claim_ids": ids, "text": _shorten(b.text, inp.max_words_per_bullet + 8)}))
            slides.append(sl.model_copy(update={"bullets": bullets, "title": clip(sl.title, 130) or s.title, "layout": s.layout,
                                               "chart_id": sl.chart_id if sl.chart_id in charts else None,
                                               "asset_ids": [a for a in sl.asset_ids if a in assets][:2], "notes": clip(sl.notes, 600)}))
        if not slides or not any(sl.bullets for sl in slides) and s.claims:
            return self.rules(inp)
        return SlideWriterOutput(slides=slides[:6])


def _shorten(text: str, max_words: int) -> str:
    w = text.split()
    return text if len(w) <= max_words else " ".join(w[:max_words]).rstrip(",;:") + "…"
