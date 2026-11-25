"""What the slide agents share: the layout catalogue, the block model and the checks every agent applies to blocks it returns.

The catalogue mirrors backend/app/core/slides/layouts.json (names, slots, capacity). The backend validates and fits the result again before it
is shown; these checks keep the agents from returning ids or structures that do not exist.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SLOT_TYPES = {"kpis": "kpis", "chart": "chart", "bullets": "bullets", "bullets2": "bullets", "table": "table", "callout": "callout", "image": "image"}

LAYOUTS: dict[str, dict] = {
    "exec-summary": {"slots": ["kpis", "bullets", "callout"], "use": "Management summary: 3-4 key figures, 3-5 key messages, the decision requested."},
    "kpi-chart": {"slots": ["kpis", "chart", "bullets"], "use": "Key figures on top, one chart, 2-4 bullets with the reading of the chart."},
    "chart-text": {"slots": ["chart", "bullets"], "use": "Large chart left, 2-5 bullets right."},
    "text-chart": {"slots": ["bullets", "chart"], "use": "Bullets left, large chart right."},
    "kpi-bullets": {"slots": ["kpis", "bullets"], "use": "2-4 key figures and 3-6 bullets below (no chart)."},
    "bullets": {"slots": ["bullets"], "use": "Plain text, 3-6 bullets. Use only when nothing is quantified."},
    "two-column": {"slots": ["bullets", "bullets2"], "use": "Two lists side by side (pros/cons, today/target, risks/measures)."},
    "table": {"slots": ["table"], "use": "A comparison table, up to 10 rows x 6 columns."},
    "table-text": {"slots": ["table", "bullets"], "use": "Table (up to 4-5 rows) with 2-3 bullets below."},
    "table-callout": {"slots": ["table", "callout"], "use": "Comparison table with the conclusion in a highlighted box."},
    "image-text": {"slots": ["image", "bullets"], "use": "A picture from the sources with bullets."},
    "decision": {"slots": ["callout", "bullets", "bullets2"], "use": "Decision slide: the proposed resolution (callout), reasons (bullets), next steps (bullets2)."},
}

LAYOUT_HELP = "\n".join(f'- "{k}": slots {v["slots"]}. {v["use"]}' for k, v in LAYOUTS.items())

BLOCK_HELP = """Blocks (each has "slot" and "type"; the slot decides the type):
- slot "kpis", type "kpis": "items": 2-4 of {"value": "12,0", "unit": "Mio. €", "label": "what it is, with object and period", "delta": "+3,2 Mio. €" (optional), "tone": "up"|"down"|"neutral", "claim_ids": [...], "calc_ids": [...]}.
  "value" is the number as written in the sources or calculations (same value, same decimals), in German notation for "de".
- slot "chart", type "chart": "chart": {"type": "column"|"bar"|"line"|"donut"|"stacked", "title": "what, unit, period", "unit": "Mio. €", "labels": [...], "series": [{"name": "...", "values": [numbers]}], "highlight": index or null}, "claim_ids": [...], "calc_ids": [...].
  Use only the charts offered in the request (same labels and values; you may change type, title and highlight).
- slot "bullets" / "bullets2", type "bullets": "items": [{"text": "...", "claim_ids": [...]}] (at most 6, each at most 22 words, one idea).
- slot "table", type "table": "header": [...], "rows": [[...]], "highlight_row": index or null, "claim_ids": [...], "calc_ids": [...]. Cells hold values from the request only.
- slot "callout", type "callout": "title": "short label", "text": "one or two sentences", "tone": "decision"|"info"|"warn"|"good", "claim_ids": [...].
- slot "image", type "image": "asset_id": id of an offered image, "caption": "..." ."""


class Block(BaseModel):
    model_config = ConfigDict(extra="ignore")
    slot: str
    type: Literal["kpis", "chart", "bullets", "table", "callout", "image"]
    items: list[dict] = Field(default_factory=list)
    chart: dict | None = None
    header: list[str] = Field(default_factory=list)
    rows: list[list[str]] = Field(default_factory=list)
    highlight_row: int | None = None
    title: str = ""
    text: str = ""
    tone: str | None = None
    asset_id: str | None = None
    caption: str = ""
    claim_ids: list[str] = Field(default_factory=list)
    calc_ids: list[str] = Field(default_factory=list)


class SlideSpecOut(BaseModel):
    model_config = ConfigDict(extra="ignore")
    layout: str
    title: str
    blocks: list[Block] = Field(default_factory=list)
    notes: str = ""


class Number(BaseModel):
    """A figure of the ledger a slide may show: from an approved claim's evidence or from a calculation done in code."""
    ref: str
    label: str
    text: str  # as it may be written on a slide, e.g. "12,0"
    value: float
    unit: str | None = None
    entity: str | None = None
    period: str | None = None
    claim_ids: list[str] = Field(default_factory=list)
    calc_ids: list[str] = Field(default_factory=list)


def check_blocks(blocks: list[Block], layout: str, *, claim_ids: set[str], calc_ids: set[str], assets: set[str], unlinked_ok: set[str] | None = None) -> list[Block]:
    """Drops what cannot stand: wrong slots, unknown ids, empty blocks. Never invents anything. `unlinked_ok` names slots whose
    bullets may stand without a claim (next steps proposed to the committee; wording the author asked for)."""
    if layout not in LAYOUTS:
        return []
    slots = LAYOUTS[layout]["slots"]
    out, used = [], set()
    for b in blocks:
        if b.slot not in slots or b.slot in used or SLOT_TYPES.get(b.slot) != b.type:
            continue
        cl = [i for i in b.claim_ids if i in claim_ids]
        ca = [i for i in b.calc_ids if i in calc_ids]
        upd: dict = {"claim_ids": cl, "calc_ids": ca}
        if b.type in ("bullets", "kpis"):
            items = []
            for it in b.items:
                if isinstance(it, str):
                    it = {"text": it}
                it = dict(it)
                it["claim_ids"] = [i for i in it.get("claim_ids", []) if i in claim_ids]
                if b.type == "kpis":
                    it["calc_ids"] = [i for i in it.get("calc_ids", []) if i in calc_ids]
                    if not (it["claim_ids"] or it["calc_ids"]):
                        continue  # a key figure without its source is not shown
                elif not (it.get("text") or "").strip() or (not it["claim_ids"] and b.slot not in (unlinked_ok or set())):
                    continue  # a bullet without an approved claim behind it is dropped
                items.append(it)
            if not items:
                continue
            upd["items"] = items
        elif b.type == "chart":
            c = dict(b.chart or {})
            if not c.get("labels") or not c.get("series") or not (cl or ca):
                continue
            upd["chart"] = c
        elif b.type == "table":
            if not b.rows or not (cl or ca):
                continue
        elif b.type == "callout":
            if not b.text.strip():
                continue
        elif b.type == "image":
            if b.asset_id not in assets:
                continue
        out.append(b.model_copy(update=upd))
        used.add(b.slot)
    return out
