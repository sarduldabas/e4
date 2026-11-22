"""Agent 12: feedback-interpreter. Turns free-text feedback on the deck into structured changes."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .util import clip, overlap, pick, tokens

Lang = Literal["de", "en"]


class DeckSlide(BaseModel):
    id: str
    index: int
    section_key: str
    title: str
    claim_ids: list[str] = Field(default_factory=list)


class FeedbackInput(BaseModel):
    lang: Lang = "de"
    feedback: str
    slides: list[DeckSlide] = Field(default_factory=list)
    sections: list[tuple[str, str]] = Field(default_factory=list)  # (key, title)
    selected_slide_id: str | None = None


class Change(BaseModel):
    action: Literal["rewrite_text", "change_claim", "add_content", "remove_content", "reorder", "recalculate", "research_more", "restyle"]
    section_key: str | None = None
    slide_id: str | None = None
    claim_id: str | None = None
    instruction: str
    rerun_from: Literal["slides", "analysis", "collection"] = "slides"


class FeedbackOutput(BaseModel):
    changes: list[Change] = Field(default_factory=list)
    clarification: str | None = None


class FeedbackInterpreter(BaseAgent[FeedbackInput, FeedbackOutput]):
    id = "feedback-interpreter"
    name = "Feedback interpreter"
    stage = 3
    tier = "standard"
    description = "Turns free-text feedback on the finished deck into structured changes with the right re-run point."
    input_model = FeedbackInput
    output_model = FeedbackOutput
    system = """
The user gives feedback on a finished deck. Convert it into a list of changes, each addressing ONE slide or section.
Actions: rewrite_text (wording only; rerun_from "slides"), change_claim (a fact or figure is wrong or must change; rerun_from "analysis"),
add_content / remove_content (rerun_from "analysis" if it needs new claims, else "slides"), reorder ("slides"), recalculate ("analysis"),
research_more (new sources needed; "collection"), restyle (look only; "slides").
Refer to slides and sections only by ids/keys from the request ("selected_slide_id" is the slide the user was looking at; use it
when the feedback says "this slide" or does not say which). "instruction": what to do, one clear sentence, in the user's words.
If the feedback is too vague to act on, return no changes and ask ONE short question in "clarification"."""

    def rules(self, inp: FeedbackInput) -> FeedbackOutput:
        lang = inp.lang
        changes: list[Change] = []
        for part in [p.strip() for p in re.split(r"[.;\n]+|\bund außerdem\b|\band also\b", inp.feedback) if len(p.strip()) > 6]:
            low = part.lower()
            sl = _find_slide(part, inp)
            if any(w in low for w in ("recalcul", "neu berechn", "rechne", "calculate", "summe", "total")):
                action, rf = "recalculate", "analysis"
            elif any(w in low for w in ("falsch", "wrong", "incorrect", "stimmt nicht", "nicht korrekt", "korrigier", "correct the")):
                action, rf = "change_claim", "analysis"
            elif any(w in low for w in ("mehr zu", "recherch", "more on", "research", "quelle", "source")):
                action, rf = "research_more", "collection"
            elif any(w in low for w in ("lösch", "entfern", "remove", "delete", "streich", "weglassen")):
                action, rf = "remove_content", "slides"
            elif any(w in low for w in ("hinzufüg", "ergänz", "add ", "include", "zusätzlich")):
                action, rf = "add_content", "analysis"
            elif any(w in low for w in ("reihenfolge", "verschieb", "order", "move", "vorne", "nach hinten")):
                action, rf = "reorder", "slides"
            elif any(w in low for w in ("farbe", "color", "colour", "schrift", "font", "layout", "design")):
                action, rf = "restyle", "slides"
            else:
                action, rf = "rewrite_text", "slides"
            changes.append(Change(action=action, rerun_from=rf, slide_id=sl.id if sl else inp.selected_slide_id, section_key=sl.section_key if sl else _find_section(part, inp), instruction=clip(part, 240)))
        if not changes:
            return FeedbackOutput(clarification=pick(lang, "Was genau soll geändert werden, und auf welcher Folie?", "What exactly should change, and on which slide?"))
        return FeedbackOutput(changes=changes[:12])

    def clean(self, inp: FeedbackInput, out: FeedbackOutput) -> FeedbackOutput:
        slides = {s.id: s for s in inp.slides}
        keys = {k for k, _ in inp.sections} | {s.section_key for s in inp.slides}
        claims = {c for s in inp.slides for c in s.claim_ids}
        order = {"slides": 0, "analysis": 1, "collection": 2}
        need = {"change_claim": "analysis", "recalculate": "analysis", "research_more": "collection"}
        good = []
        for c in out.changes:
            sid = c.slide_id if c.slide_id in slides else None
            sk = c.section_key if c.section_key in keys else (slides[sid].section_key if sid else None)
            rf = c.rerun_from
            if c.action in need and order[rf] < order[need[c.action]]:
                rf = need[c.action]  # a changed fact can not be fixed by rewording slides
            good.append(c.model_copy(update={"slide_id": sid, "section_key": sk, "claim_id": c.claim_id if c.claim_id in claims else None, "rerun_from": rf, "instruction": clip(c.instruction, 300)}))
        clar = out.clarification if not good else None
        if not good and not clar:
            clar = pick(inp.lang, "Was genau soll geändert werden?", "What exactly should change?")
        return FeedbackOutput(changes=good[:12], clarification=clar)


def _find_slide(text: str, inp: FeedbackInput):
    m = re.search(r"(?:folie|slide|seite|page)\s*(\d+)", text, re.I)
    if m:
        n = int(m.group(1))
        return next((s for s in inp.slides if s.index == n), None)
    t = tokens(text)
    best = max(inp.slides, key=lambda s: overlap(tokens(s.title), t), default=None)
    return best if best and overlap(tokens(best.title), t) >= 0.4 else None


def _find_section(text: str, inp: FeedbackInput) -> str | None:
    t = tokens(text)
    best = max(inp.sections, key=lambda kt: overlap(tokens(kt[1]), t), default=None)
    return best[0] if best and overlap(tokens(best[1]), t) >= 0.4 else None
