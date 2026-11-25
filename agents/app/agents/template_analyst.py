"""Agent 1: template-analyst. Turns the structure of the PPT template into an editable outline."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .core import BaseAgent
from .knowledge import DEFAULT_OUTLINE, TOPICS, classify, i, topic_by_key
from .util import clip, pick, slug

Lang = Literal["de", "en"]
SKIP_TITLES = ("agenda", "inhalt", "contents", "table of contents", "thank", "dank", "questions", "fragen", "backup", "appendix", "anhang")


class TemplateSlide(BaseModel):
    index: int
    title: str | None = None
    layout: str | None = None
    text: list[str] = Field(default_factory=list)
    has_chart: bool = False
    has_image: bool = False


class TemplateInfo(BaseModel):
    name: str = ""
    slide_count: int = 0
    layouts: list[str] = Field(default_factory=list)
    slides: list[TemplateSlide] = Field(default_factory=list)


class TemplateAnalystInput(BaseModel):
    lang: Lang = "de"
    topic: str = ""
    description: str = ""
    committee: str | None = None
    decision_requested: str = ""
    template: TemplateInfo | None = None


class OutlineSection(BaseModel):
    key: str
    title: str
    purpose: str = ""
    layout: str | None = None  # name of a layout in the template
    required_inputs: list[str] = Field(default_factory=list)
    suggested_slides: int = 1


class TemplateAnalystOutput(BaseModel):
    sections: list[OutlineSection]
    notes: str | None = None


class TemplateAnalyst(BaseAgent[TemplateAnalystInput, TemplateAnalystOutput]):
    id = "template-analyst"
    name = "Template analyst"
    stage = 1
    tier = "strong"
    description = "Turns the PPT template into an editable outline with the inputs each section needs."
    input_model = TemplateAnalystInput
    output_model = TemplateAnalystOutput
    system = """
You receive the structure of the committee's PowerPoint template (slide titles, layout names, the text on each slide,
whether a slide holds a chart or an image) plus the topic and description of the report.
Propose the outline of the report: one entry per content section the template expects, in template order.
- Skip title, agenda, thank-you, questions and appendix slides. Merge slides that obviously belong together.
- "purpose": one sentence on what the section must tell the committee.
- "layout": the template layout best suited to the section, copied exactly from template.layouts, or null.
- "required_inputs": 1-4 concrete pieces of information the user must provide or the sources must contain for the section
  to be written well (for example "cost per option", "milestones with dates"). Tailor them to the topic.
- "suggested_slides": how many slides the section needs (usually 1).
If NO template is given, you advise the structure yourself: design the outline of a board-level paper for THIS topic, committee and
decision requested, not a generic one. Think about what the committee must understand and weigh to decide: the situation and why a
decision is needed now, the options and how they compare (cost, risk, time, strategic fit), the evidence and market context, the risks and how
they are mitigated, the financial and timeline consequences, and the recommendation with next steps. Use 6-9 sections, the decision-relevant
ones first, with concrete "required_inputs" (which figures, comparisons, dates and documents are needed). Do not add the management summary or
the decision slide as sections: the deck gets both automatically. Say in "notes" in one or two sentences why you structured it this way.
Section keys: short lowercase ascii slugs, unique."""

    def rules(self, inp: TemplateAnalystInput) -> TemplateAnalystOutput:
        lang = inp.lang
        sections: list[OutlineSection] = []
        seen: set[str] = set()
        t = inp.template
        if t and t.slides:
            for s in t.slides:
                title = (s.title or "").strip()
                if not title or any(w in title.lower() for w in SKIP_TITLES):
                    continue
                if s.index == 1 and len(t.slides) > 1 and not s.has_chart and not s.has_image and (s.layout or "").lower().startswith("title"):
                    continue
                key = slug(title)
                if key in seen:
                    continue
                seen.add(key)
                topic = classify(title)
                sections.append(OutlineSection(
                    key=key, title=title,
                    purpose=i(lang, topic[3]) if topic else pick(lang, "Die wichtigsten Fakten zu diesem Abschnitt", "The key facts for this section"),
                    layout=s.layout,
                    required_inputs=[i(lang, x) for x in topic[4]] if topic else [pick(lang, f"Die wichtigsten Fakten zu „{clip(title, 40)}“", f"The key facts for “{clip(title, 40)}”")],
                ))
        notes = None
        if not sections:
            for key in DEFAULT_OUTLINE:
                tp = topic_by_key(key)
                sections.append(OutlineSection(key=key, title=i(lang, tp[2]), purpose=i(lang, tp[3]), required_inputs=[i(lang, x) for x in tp[4]]))
            notes = pick(lang, "Kein Template mit Inhaltsfolien erkannt: Standardgliederung verwendet.", "No template with content slides found: standard outline used.")
        return TemplateAnalystOutput(sections=sections[:14], notes=notes)

    def clean(self, inp: TemplateAnalystInput, out: TemplateAnalystOutput) -> TemplateAnalystOutput:
        layouts = set(inp.template.layouts) if inp.template else set()
        keys: set[str] = set()
        good: list[OutlineSection] = []
        for s in out.sections:
            key = slug(s.key or s.title)
            while key in keys:
                key += "-2"
            keys.add(key)
            good.append(s.model_copy(update={
                "key": key, "title": clip(s.title, 90) or key, "layout": s.layout if s.layout in layouts else None,
                "required_inputs": [clip(x, 120) for x in s.required_inputs if x.strip()][:4],
                "suggested_slides": min(max(s.suggested_slides, 1), 4)}))
        return out.model_copy(update={"sections": good[:14]})
