"""Agent: slide-writer. Turns the approved claims of one section into finished slide specs (layout, action title, key figures, chart, table, bullets)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .section_analyst import ChartSpec, Claim
from .slides_common import BLOCK_HELP, LAYOUT_HELP, Block, Number, SlideSpecOut, check_blocks
from .util import clip, pick

Lang = Literal["de", "en"]


class SlideAsset(BaseModel):
    id: str
    kind: Literal["image", "table", "chart"]
    caption: str = ""
    table: list[list[str]] | None = None  # the rows of a table taken from a source (first row = header)


class SlideSection(BaseModel):
    key: str
    title: str
    layout: str | None = None  # a wish from the outline; may be ignored
    suggested_slides: int = 1
    headline: str = ""
    claims: list[Claim] = Field(default_factory=list)  # approved only
    charts: list[ChartSpec] = Field(default_factory=list)
    assets: list[SlideAsset] = Field(default_factory=list)
    open_points: list[str] = Field(default_factory=list)


class Storyline(BaseModel):
    deck_title: str = ""
    summary_title: str = ""
    index: int = 1
    count: int = 1
    slides: int = 1  # how many slides this section gets


class SlideIssue(BaseModel):
    slide: int | None = None
    message: str


class SlideWriterInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    committee: str | None = None
    section: SlideSection
    numbers: list[Number] = Field(default_factory=list)  # figures of this section a slide may show
    storyline: Storyline = Field(default_factory=Storyline)
    instruction: str | None = None
    previous_slides: list[SlideSpecOut] = Field(default_factory=list)
    issues: list[SlideIssue] = Field(default_factory=list)  # from the checks after a first attempt


class SlideWriterOutput(BaseModel):
    slides: list[SlideSpecOut]


class SlideWriter(BaseAgent[SlideWriterInput, SlideWriterOutput]):
    id = "slide-writer"
    name = "Slide writer"
    stage = 3
    tier = "strong"
    description = "Turns the approved claims of a section into finished slides: action title, key figures, chart, table, bullets, speaker notes."
    input_model = SlideWriterInput
    output_model = SlideWriterOutput
    system = f"""
You design the slides for ONE section of a board paper, from its approved claims. Senior executives read them: every slide carries one message,
shows the numbers behind it, and could be presented as it is.
For each slide ("storyline.slides" slides; fewer only if the content is thin) return layout, title, blocks, notes.
- "title": the message of the slide as a full sentence with its decisive number or consequence (max 16 words). Never a topic label ("Kosten", "Überblick").
- Choose the layout by what the content is: quantified comparison -> "kpi-chart" or "chart-text"; options against criteria -> "table-callout" or "table"; share of a whole -> chart "donut";
  development over time -> chart "line"; two-sided (pros/cons, risks/measures) -> "two-column"; only qualitative statements -> "bullets" (avoid when numbers exist).
  Do not repeat a layout on consecutive slides if another one fits as well.
- Show numbers visually: key figures (kpis) for the 2-4 numbers the message rests on, a chart for any comparison or development of 2-12 comparable values, a table for
  option-by-criterion comparisons. Take values ONLY from "numbers" (use their "text" as written), from the offered "charts" and from the claims. Never compute, round,
  convert or invent a figure. A table or chart row you cannot fill from the request is left out.
- Bullets: at most 5 per slide, at most 22 words each, each tied to claim ids; state the reading of the numbers ("so what"), not a repetition of the visual.
- "notes": speaker notes in 3-5 sentences: what to say beyond the slide, the caveats and the open points of the section, from the claims only.
- Every block cites claim_ids/calc_ids that support it. Use all important approved claims across the slides; do not add statements.
If "instruction" is given, revise "previous_slides" accordingly. If "issues" are given, fix exactly those (a number not found in the ledger must be removed or replaced by one from "numbers").
{LAYOUT_HELP}
{BLOCK_HELP}"""

    # ---------------------------------------------------------------- rules
    def rules(self, inp: SlideWriterInput) -> SlideWriterOutput:
        s, lang = inp.section, inp.lang
        title = clip(s.headline or (s.claims[0].text if s.claims else s.title), 140)
        size = 4
        groups = [s.claims[i:i + size] for i in range(0, max(len(s.claims), 1), size)][: max(1, inp.storyline.slides)] or [[]]
        slides: list[SlideSpecOut] = []
        for n, g in enumerate(groups):
            blocks: list[Block] = []
            bullets = Block(slot="bullets", type="bullets", items=[{"text": clip(c.text, 200), "claim_ids": [c.id]} for c in g])
            chart = s.charts[0] if n == 0 and s.charts else None
            table = next((a for a in s.assets if a.kind == "table" and a.table), None) if n == 0 and not chart else None
            layout = "bullets"
            if chart:
                layout = "chart-text"
                cl = chart.claim_ids or [c.id for c in g[:2]]
                blocks.append(Block(slot="chart", type="chart", chart={"type": chart.type, "title": chart.title, "unit": chart.unit or "", "labels": chart.labels,
                                                                       "series": [{"name": chart.unit or "", "values": chart.values}]}, claim_ids=cl, calc_ids=chart.calc_ids))
            elif table and len(table.table or []) >= 2:
                layout = "table-text"
                blocks.append(Block(slot="table", type="table", header=table.table[0], rows=table.table[1:6], claim_ids=[c.id for c in g[:2]]))
            blocks.append(bullets)
            slides.append(SlideSpecOut(layout=layout, title=title if n == 0 else clip(f"{title} ({n + 1})", 150), blocks=blocks,
                                       notes=" ".join(c.text for c in g[:3]) + ((" " + pick(lang, "Offen: ", "Open: ") + "; ".join(s.open_points[:3])) if s.open_points and n == 0 else "")))
        return SlideWriterOutput(slides=slides)

    # ---------------------------------------------------------------- guard rails
    def clean(self, inp: SlideWriterInput, out: SlideWriterOutput) -> SlideWriterOutput:
        s = inp.section
        claim_ids = {c.id for c in s.claims}
        calc_ids = {i for n in inp.numbers for i in n.calc_ids} | {i for ch in s.charts for i in ch.calc_ids}
        assets = {a.id for a in s.assets if a.kind == "image"}
        slides = []
        for sl in out.slides:
            blocks = check_blocks(sl.blocks, sl.layout, claim_ids=claim_ids, calc_ids=calc_ids, assets=assets)
            if blocks:
                slides.append(sl.model_copy(update={"blocks": blocks, "title": clip(sl.title, 150) or s.title, "notes": clip(sl.notes, 1800)}))
        if not slides and s.claims:
            return self.rules(inp)
        return SlideWriterOutput(slides=slides[:5])
