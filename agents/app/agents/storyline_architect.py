"""Agent: storyline-architect. Plans the executive layer of the deck: the answer-first summary and the decision slide."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .slides_common import BLOCK_HELP, Block, Number, SlideSpecOut, check_blocks
from .util import clip, pick

Lang = Literal["de", "en"]


class ArchClaim(BaseModel):
    id: str
    text: str
    kind: str = "fact"


class ArchSection(BaseModel):
    key: str
    title: str
    headline: str = ""
    claims: list[ArchClaim] = Field(default_factory=list)  # approved only
    open_points: list[str] = Field(default_factory=list)


class StorylineInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    committee: str | None = None
    decision_requested: str = ""
    description: str = ""
    sections: list[ArchSection] = Field(default_factory=list)
    numbers: list[Number] = Field(default_factory=list)  # the figures a key-figure tile may show
    challenges: list[str] = Field(default_factory=list)  # open objections of the red team, short
    calc_ids: list[str] = Field(default_factory=list)


class StorylineOutput(BaseModel):
    deck_title: str = ""
    summary: SlideSpecOut | None = None
    decision: SlideSpecOut | None = None
    slides_per_section: dict[str, int] = Field(default_factory=dict)


class StorylineArchitect(BaseAgent[StorylineInput, StorylineOutput]):
    id = "storyline-architect"
    name = "Storyline architect"
    stage = 3
    tier = "strong"
    description = "Plans the executive layer of the deck: answer-first summary with key figures, the decision slide, and how many slides each section gets."
    input_model = StorylineInput
    output_model = StorylineOutput
    system = f"""
You are the chief of staff who prepares the board paper. The deck is read by senior executives who decide in minutes. You write the two
slides they read first and the one they decide on, from the APPROVED claims of the sections. Return:
- "deck_title": the report title as a statement of what the deck asks for (max 14 words), not a topic label.
- "summary": layout "exec-summary" with blocks kpis (3-4 tiles with the decisive figures), bullets (3-5 key messages: answer first, then why, then risk) and
  callout (tone "decision": what the committee is asked to decide, one or two sentences). "title": the answer in one sentence with its key number.
  Pick the key figures from "numbers" only (their "text" as is; the tile label names object and period; "delta" only if the difference is a listed number).
  Every kpi cites claim_ids or calc_ids from its number; every bullet cites claim ids. Say what the sections say; add nothing.
- "decision": layout "decision" with blocks callout (tone "decision", title like "Beschlussvorschlag", the resolution proposed - based on "decision_requested" and the
  recommendation claims), bullets (the reasons, each with claim ids), bullets2 (next steps after the decision; if the claims contain no next steps, propose
  at most 3 obvious ones without claim ids, and never new facts, figures or dates).
  If the claims do not support a recommendation, say in the callout what is needed to decide and list the open points as reasons - do not recommend.
- "slides_per_section": for each section key how many slides it deserves (1-3): more where there is more to quantify or compare.
Open objections ("challenges") belong in the key messages or next steps where they change the decision.
{BLOCK_HELP}"""

    def rules(self, inp: StorylineInput) -> StorylineOutput:
        lang = inp.lang
        first = [(s, s.claims[0]) for s in inp.sections if s.claims]
        kp = []
        for n in inp.numbers[:3]:
            kp.append({"value": n.text, "unit": n.unit or "", "label": clip(n.label, 60), "claim_ids": n.claim_ids[:2], "calc_ids": n.calc_ids[:2]})
        blocks = []
        if kp:
            blocks.append(Block(slot="kpis", type="kpis", items=kp))
        if first:
            blocks.append(Block(slot="bullets", type="bullets", items=[{"text": clip(s.headline or c.text, 190), "claim_ids": [c.id]} for s, c in first[:5]]))
        blocks.append(Block(slot="callout", type="callout", title=pick(lang, "Beschlussvorschlag", "Decision requested"), tone="decision",
                            text=clip(inp.decision_requested or pick(lang, "Das Gremium wird um Kenntnisnahme gebeten.", "The committee is asked to take note."), 400)))
        title = clip(inp.sections[0].headline, 150) if inp.sections and inp.sections[0].headline else clip(inp.topic, 150)
        reasons = [{"text": clip(c.text, 190), "claim_ids": [c.id]} for s in inp.sections for c in s.claims if c.kind in ("recommendation", "analysis")][:4]
        dblocks = [Block(slot="callout", type="callout", title=pick(lang, "Beschlussvorschlag", "Proposed resolution"), tone="decision",
                         text=clip(inp.decision_requested or pick(lang, "Das Gremium wird um Kenntnisnahme gebeten.", "The committee is asked to take note."), 400))]
        if reasons:
            dblocks.append(Block(slot="bullets", type="bullets", items=reasons))
        return StorylineOutput(deck_title=clip(inp.topic, 120), summary=SlideSpecOut(layout="exec-summary", title=title, blocks=blocks),
                               decision=SlideSpecOut(layout="decision", title=pick(lang, "Beschlussvorschlag", "Proposed resolution"), blocks=dblocks),
                               slides_per_section={s.key: 1 for s in inp.sections})

    def clean(self, inp: StorylineInput, out: StorylineOutput) -> StorylineOutput:
        claim_ids = {c.id for s in inp.sections for c in s.claims}
        calc_ids = {i for n in inp.numbers for i in n.calc_ids} | set(inp.calc_ids)
        res = {}
        for name, layout, unl in (("summary", "exec-summary", set()), ("decision", "decision", {"bullets2"})):
            sp = getattr(out, name)
            if sp is None:
                continue
            blocks = check_blocks(sp.blocks, layout, claim_ids=claim_ids, calc_ids=calc_ids, assets=set(), unlinked_ok=unl)
            if blocks:
                res[name] = sp.model_copy(update={"layout": layout, "blocks": blocks, "title": clip(sp.title, 150), "notes": clip(sp.notes, 900)})
        keys = {s.key for s in inp.sections}
        per = {k: max(1, min(3, int(v))) for k, v in out.slides_per_section.items() if k in keys}
        fb = None if res.get("summary") and res.get("decision") else self.rules(inp)
        return StorylineOutput(deck_title=clip(out.deck_title or inp.topic, 140), summary=res.get("summary") or fb.summary, decision=res.get("decision") or fb.decision,
                               slides_per_section={k: per.get(k, 1) for k in keys})
