"""Agent: slide-editor. Applies a reviewer's comment to ONE slide and returns the revised slide."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .section_analyst import ChartSpec
from .slide_writer import SlideAsset
from .slides_common import BLOCK_HELP, LAYOUT_HELP, Number, SlideSpecOut, check_blocks
from .util import clip, pick

Lang = Literal["de", "en"]


class EditClaim(BaseModel):
    id: str
    text: str
    kind: str = "fact"


class SlideEditorInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    slide: SlideSpecOut
    instruction: str  # the reviewer's comment, in their words
    claims: list[EditClaim] = Field(default_factory=list)  # approved claims of the section (and of the slide)
    numbers: list[Number] = Field(default_factory=list)
    charts: list[ChartSpec] = Field(default_factory=list)
    assets: list[SlideAsset] = Field(default_factory=list)
    other_titles: list[str] = Field(default_factory=list)  # titles of the neighbouring slides, to avoid repetition


class SlideEditorOutput(BaseModel):
    slide: SlideSpecOut
    summary: str = ""  # one sentence: what was changed
    needs: list[str] = Field(default_factory=list)  # what could not be done and why (e.g. a figure that is not in the sources)


class SlideEditor(BaseAgent[SlideEditorInput, SlideEditorOutput]):
    id = "slide-editor"
    name = "Slide editor"
    stage = 3
    tier = "strong"
    description = "Applies a reviewer's comment to one slide (wording, emphasis, layout, chart, table) without leaving the evidence."
    input_model = SlideEditorInput
    output_model = SlideEditorOutput
    system = f"""
A reviewer comments on ONE slide of a board paper ("instruction"). Return the revised slide ("slide"), a one-sentence "summary" of what you changed in the
language of the report, and "needs": what you could not do and why.
- Change only what the comment asks for; keep everything else of the slide exactly as it is (same claim ids, same numbers).
- You may reword, shorten, reorder, change the title, switch the layout or the chart type, highlight a bar, add or remove a bullet, build a table or key figures
  from "numbers", or use another offered chart or claim.
- Facts and figures come from "claims", "numbers", "charts" and the current slide only. If the comment asks for a figure or statement that is not there, do not
  invent it: keep the slide and name the gap in "needs". Text and numbers that the reviewer writes in the comment itself are the reviewer's own and may be put
  on the slide as written (bullets without claim ids).
- Keep the title a full-sentence message. Keep at most 5-6 bullets of at most 22 words. Update "notes" when the content changes.
{LAYOUT_HELP}
{BLOCK_HELP}"""

    def rules(self, inp: SlideEditorInput) -> SlideEditorOutput:
        return SlideEditorOutput(slide=inp.slide, summary="", needs=[pick(inp.lang, "Die Änderung benötigt das Sprachmodell; die Folie blieb unverändert.", "This change needs the language model; the slide was left unchanged.")])

    def clean(self, inp: SlideEditorInput, out: SlideEditorOutput) -> SlideEditorOutput:
        claim_ids = {c.id for c in inp.claims}
        for b in inp.slide.blocks:  # claims the slide already cites stay valid
            claim_ids |= set(b.claim_ids) | {i for it in b.items for i in it.get("claim_ids", [])}
        calc_ids = {i for n in inp.numbers for i in n.calc_ids} | {i for ch in inp.charts for i in ch.calc_ids}
        for b in inp.slide.blocks:
            calc_ids |= set(b.calc_ids) | {i for it in b.items for i in it.get("calc_ids", [])}
        assets = {a.id for a in inp.assets if a.kind == "image"} | {b.asset_id for b in inp.slide.blocks if b.asset_id}
        sl = out.slide
        blocks = check_blocks(sl.blocks, sl.layout, claim_ids=claim_ids, calc_ids=calc_ids, assets=assets, unlinked_ok={"bullets", "bullets2"})
        if not blocks:
            return SlideEditorOutput(slide=inp.slide, summary="", needs=out.needs + [pick(inp.lang, "Die Änderung konnte nicht umgesetzt werden; die Folie blieb unverändert.", "The change could not be applied; the slide was left unchanged.")])
        return SlideEditorOutput(slide=sl.model_copy(update={"blocks": blocks, "title": clip(sl.title, 150) or inp.slide.title, "notes": clip(sl.notes or inp.slide.notes, 1800)}),
                                 summary=clip(out.summary, 240), needs=[clip(n, 240) for n in out.needs][:4])
