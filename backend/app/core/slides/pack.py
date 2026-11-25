"""Which slides share a page in the PowerPoint file.

Sections differ in length: one needs half a slide, another three. The author does not arrange this by hand. When the file is made, a short text-only
slide of one section and the next section's short text-only slide are put on one page (each under its own heading), as long as the first page is
less than three quarters full and both fit together. Everything else (charts, tables, key figures, pictures, the summary, the decision) keeps its own
slide. The slides on the web page are not changed: only the file is packed, and the author can still move things around in PowerPoint afterwards.
"""
from __future__ import annotations

from . import fit
from .spec import layouts

REF = 18          # font size used to judge how full a slide is (the real size is chosen later, so that the text fits)
START_NEW = 0.75  # a page that is already this full is not shared
LIMIT = 0.95      # what two or three parts may add up to
HEADING = 0.07    # room for the heading line of each part
MAX_PARTS = 3
MAX_ITEMS = 10


def text_fill(spec: dict) -> float | None:
    """Share of the text area that a text-only content slide fills at the reference size; None for any other slide."""
    if spec.get("kind") != "content" or not spec["blocks"] or any(b["type"] != "bullets" for b in spec["blocks"]):
        return None
    box = layouts()["layouts"]["bullets"]["slots"]["bullets"]
    items = [i["text"] for b in spec["blocks"] for i in b["items"]]
    inner = box["w"] - 2 * fit.PAD - REF * 1.4
    total = sum(fit.lines(t, REF, inner) * REF * fit.LINE_H for t in items) + (len(items) - 1) * REF * 0.6 + 2 * fit.PAD
    return total / box["h"]


def plan(specs: list[dict], sections: list[str]) -> list[list[int]]:
    """Groups of consecutive slide indexes; a group of more than one becomes one page. `sections` is the section key of each slide."""
    groups: list[list[int]] = []
    i, n = 0, len(specs)
    while i < n:
        group = [i]
        fill = text_fill(specs[i])
        if fill is not None:
            used = fill + HEADING
            count = sum(len(b["items"]) for b in specs[i]["blocks"]) + 1
            j = i + 1
            while j < n and len(group) < MAX_PARTS and used < START_NEW:
                nxt = text_fill(specs[j])
                if nxt is None or sections[j] == sections[group[-1]] or used + nxt + HEADING > LIMIT:
                    break
                items = sum(len(b["items"]) for b in specs[j]["blocks"]) + 1
                if count + items > MAX_ITEMS:
                    break
                group.append(j)
                used += nxt + HEADING
                count += items
                j += 1
        groups.append(group)
        i += len(group)
    return groups


def merge(parts: list[dict], section_titles: list[str]) -> dict:
    """One slide from several short ones: the sections' titles as the title, each part's own title as a heading above its points."""
    items: list[dict] = []
    for sp in parts:
        items.append({"text": sp["title"], "claim_ids": [], "level": 0, "heading": True})
        items += [dict(i) for b in sp["blocks"] for i in b["items"]]
    notes = "\n\n".join(x for x in (sp.get("notes", "") for sp in parts) if x)
    return {"layout": "bullets", "kind": "content", "title": " · ".join(dict.fromkeys(section_titles)), "notes": notes,
            "blocks": [{"slot": "bullets", "type": "bullets", "items": items}]}
