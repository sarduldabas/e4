"""The asset library: every picture, chart and table found in the sources is stored, looked at, cropped where needed, described, and offered to the slides.

  1. store      code      pictures cut out of PDFs, Office files, mails and web pages; chart data of PowerPoint charts; tables
  2. assess     vision    the asset-analyst looks at each picture: kind, usability, crop box of the real figure, chart data to redraw it
  3. redraw     code      chart data becomes evidence (so the numbers are in the ledger) and the analysis draws a native, editable chart from it
  4. curate     agent     the asset-curator chooses, from the whole catalogue, what belongs on which section's slides
The user has the last word: `user_choice` ("use" / "skip") beats the curator.
"""
from __future__ import annotations

import hashlib
import re
from concurrent.futures import ThreadPoolExecutor

from ..core.ingest.figures import crop_fraction
from ..core.ingest.model import Parsed
from ..core.parsers import thumbnail_data_url
from ..core.storage import safe_name
from ..models import Asset, Evidence, Slide, Source
from .ctx import Context, log_event

MAX_PER_SOURCE = 40
BATCH = 6
_WORD = re.compile(r"[^\W_]{4,}")


def _words(text: str) -> set[str]:
    return {w[:6] for w in _WORD.findall((text or "").lower())}


def store_parsed(ctx: Context, s, rid: str, sid: str, src_title: str, p: Parsed) -> int:
    """Put what a reader found into the library. Returns the number of assets added."""
    have = {a.sha for a in s.query(Asset).filter_by(report_id=rid).all() if a.sha}
    n = 0
    for im in p.images[:MAX_PER_SOURCE]:
        if im.width and im.width < 120:
            continue
        sha = hashlib.sha1(im.data).hexdigest()
        if sha in have:
            continue
        have.add(sha)
        a = Asset(report_id=rid, source_id=sid, kind="image", caption=(im.caption or f"{src_title} – {im.locator}")[:300], width=im.width, height=im.height,
                  context=(im.context or f"{im.locator} {src_title}")[:1500], origin=im.origin, locator=im.locator[:200], sha=sha, rights=(im.rights or None), analysed=False)
        s.add(a)
        s.flush()
        a.key = ctx.store.put(f"reports/{rid}/assets/{a.id}-{safe_name('img.' + im.ext)}", im.data)
        n += 1
    for c in p.charts[:20]:  # numbers stored in the file: exact, no vision needed
        data = {"type": c.type, "title": c.title, "unit": c.unit, "labels": c.labels, "series": c.series, "printed": True}
        s.add(Asset(report_id=rid, source_id=sid, kind="chart", caption=(c.title or f"{src_title} – {c.locator}")[:300], context=f"{c.locator} {src_title} {c.title}"[:1500],
                    origin="document", locator=c.locator[:200], role="chart", chart=data, treatment="redraw", legibility=1.0, analysed=True,
                    description=f"Diagramm „{c.title}“ ({len(c.labels)} Werte, {len(c.series)} Reihe(n))" if c.title else f"Diagramm ({len(c.labels)} Werte)"))
        n += 1
    for t in p.tables[:6]:
        if len(t.rows) >= 2:
            s.add(Asset(report_id=rid, source_id=sid, kind="table", caption=(t.caption or t.locator)[:300], table=t.rows[:25], origin="document", locator=t.locator[:200],
                        context=f"{t.locator} " + " ".join(" ".join(r) for r in t.rows[:3])[:400], role="table_image", treatment="use", analysed=True))
            n += 1
    return n


# --------------------------------------------------------------------------- assess (vision)
def assess(ctx: Context, rid: str, base: dict, sections: list[dict]) -> dict:
    """Look at pictures that have not been looked at. Cropped figures become assets of their own; chart data becomes evidence."""
    with ctx.db.session() as s:
        todo = [a for a in s.query(Asset).filter_by(report_id=rid, kind="image").all() if not a.analysed and a.key]
        todo.sort(key=lambda a: -((a.width or 0) * (a.height or 0)))
        todo = todo[: ctx.settings.max_assets_analysed]
        srcs = {x.id: x.title for x in s.query(Source).filter_by(report_id=rid).all()}
        items = [{"id": a.id, "caption": a.caption, "context": (a.context or "")[:400], "source_label": srcs.get(a.source_id, ""), "width": a.width, "height": a.height, "key": a.key} for a in todo]
    stats = {"looked_at": 0, "cropped": 0, "charts": 0, "discarded": 0, "failed": 0}
    if not items:
        return stats
    secs = [{"key": x["key"], "title": x["title"]} for x in sections]
    batches = [items[i:i + BATCH] for i in range(0, len(items), BATCH)]

    def call(batch):
        payload = {**base, "sections": secs, "assets": [{k: v for k, v in it.items() if k != "key"} | {"image": thumbnail_data_url(ctx.store.get(it["key"]), 1280) or ""} for it in batch]}
        try:
            return batch, ctx.runner.run("asset-analyst", payload, report_id=rid), None
        except Exception as e:  # noqa: BLE001  the other batches continue
            return batch, None, f"{e.__class__.__name__}: {e}"[:160]

    with ThreadPoolExecutor(max_workers=max(1, ctx.settings.parallel_calls)) as pool:
        results = list(pool.map(call, batches))
    with ctx.db.session() as s:
        for batch, out, err in results:
            if err or not out:
                stats["failed"] += len(batch)
                continue
            for r in out["assets"]:
                a = s.get(Asset, r["id"])
                if not a:
                    continue
                stats["looked_at"] += 1
                a.role, a.description, a.legibility, a.treatment, a.section_hints, a.analysed = r["role"], r["description"], r["legibility"], r["treatment"], r["section_keys"], True
                if r["treatment"] == "discard":
                    stats["discarded"] += 1
                if r.get("chart"):
                    a.chart = {**r["chart"], "text": r.get("text", "")}
                    stats["charts"] += 1
                if r.get("crop") and r["treatment"] != "discard":
                    c = r["crop"]
                    cropped = crop_fraction(ctx.store.get(a.key), (c["x0"], c["y0"], c["x1"], c["y1"]))
                    if cropped:
                        data, w, h = cropped
                        sha = hashlib.sha1(data).hexdigest()
                        child = Asset(report_id=rid, source_id=a.source_id, kind="image", caption=a.caption, width=w, height=h, context=a.context, origin="crop", locator=a.locator, parent_id=a.id,
                                      role=a.role, description=a.description, legibility=a.legibility, treatment=a.treatment, chart=a.chart, section_hints=a.section_hints, analysed=True,
                                      sha=sha, rights=a.rights)
                        s.add(child)
                        s.flush()
                        child.key = ctx.store.put(f"reports/{rid}/assets/{child.id}-{safe_name('img.png')}", data)
                        a.treatment = "discard"  # superseded by the crop
                        a.description = "(ersetzt durch Ausschnitt)" if base.get("lang", "de") == "de" else "(replaced by its crop)"
                        stats["cropped"] += 1
        log_event(s, rid, "assets_assessed", **stats)
    return stats


# --------------------------------------------------------------------------- redraw: chart data -> evidence
def chart_evidence(ctx: Context, rid: str, sections: list[dict]) -> int:
    """The numbers of charts that were read (or stored in the file) enter the ledger as evidence, so analysis, checks and slides can use and verify them.
    The chart is then drawn natively from the verified numbers instead of pasting a picture."""
    added = 0
    sec_words = {x["key"]: _words(x["title"] + " " + x.get("purpose", "")) for x in sections}
    with ctx.db.session() as s:
        have = {(e.section_key, e.statement.lower()) for e in s.query(Evidence).filter_by(report_id=rid).all()}
        done_sources = {e.locator for e in s.query(Evidence).filter_by(report_id=rid, kind="number").filter(Evidence.locator.like("Diagramm:%")).all()}
        for a in s.query(Asset).filter(Asset.report_id == rid, Asset.chart.isnot(None)).all():
            if a.treatment == "discard" or a.user_choice == "skip":
                continue
            loc = f"Diagramm: {a.id}"
            if loc in done_sources:
                continue
            ch = a.chart or {}
            title = ch.get("title") or a.caption or "Diagramm"
            hint = (a.section_hints or [None])[0]
            key = hint or max(sec_words, key=lambda k: len(sec_words[k] & _words(title + " " + (a.description or "") + " " + (a.context or ""))), default="_general")
            if not hint and sec_words and not (sec_words.get(key, set()) & _words(title + " " + (a.description or "") + " " + (a.context or ""))):
                key = "_general"
            unit = ch.get("unit") or None
            printed = bool(ch.get("printed", True))
            src = s.get(Source, a.source_id) if a.source_id else None
            where = f"{src.title}, {a.locator}" if src and a.locator else (src.title if src else "")
            multi = len([x for x in ch.get("series", []) if x.get("values")]) > 1
            rows = 0
            for ser in ch.get("series", [])[:6]:
                for label, v in zip(ch.get("labels", []), ser.get("values", [])):
                    if v is None or rows >= 60:
                        continue
                    name = ser.get("name") or ""
                    stmt = f"{title}: {label}{' (' + name + ')' if multi and name else ''} = {v:g}{' ' + unit if unit else ''}"
                    sig = (key, stmt.lower())
                    if sig in have:
                        continue
                    have.add(sig)
                    is_period = bool(re.match(r"^(19|20)\d\d\b|^Q[1-4]\b|^H[12]\b", str(label)))
                    s.add(Evidence(report_id=rid, section_key=key, origin="document", source_id=a.source_id, kind="number", statement=stmt[:300],
                                   quote=(a.description or title)[:300], locator=loc, value=float(v), unit=unit, entity=None if is_period else (name or str(label))[:120],
                                   period=str(label)[:40] if is_period else None, confidence=0.85 if printed else 0.55))
                    rows += 1
                    added += 1
            if rows:
                s.add(Evidence(report_id=rid, section_key=key, origin="document", source_id=a.source_id, kind="fact",
                               statement=f"Quelle zeigt ein Diagramm „{title}“: {a.description or ''}"[:300], quote=(a.description or title)[:300], locator=loc, confidence=0.8 if printed else 0.55))
                added += 1
                if where:
                    a.caption = (a.caption or title)[:300]
        if added:
            log_event(s, rid, "chart_data_added", evidence=added)
    return added


# --------------------------------------------------------------------------- curate
def curate(ctx: Context, rid: str, base: dict, sections: list[dict]) -> int:
    with ctx.db.session() as s:
        srcs = {x.id: x.title for x in s.query(Source).filter_by(report_id=rid).all()}
        rows = [a for a in s.query(Asset).filter_by(report_id=rid).all() if a.user_choice != "skip" and a.treatment != "discard" and not (a.kind == "image" and not a.key)]
        rows.sort(key=lambda a: (a.user_choice != "use", -((a.width or 0) * (a.height or 0)), a.id))
        cand = [{"id": a.id, "kind": a.kind, "caption": a.caption, "context": (a.context or "")[:500], "source_label": srcs.get(a.source_id, ""), "width": a.width, "height": a.height,
                 "role": a.role or "", "description": a.description or "", "legibility": a.legibility, "treatment": a.treatment or "", "origin": a.origin or "",
                 "has_data": bool(a.chart), "section_hints": a.section_hints or []} for a in rows[:80]]
        for a in s.query(Asset).filter_by(report_id=rid).all():
            if a.user_choice is None:
                a.chosen, a.section_key = False, None
    if not cand:
        return 0
    out = ctx.runner.run("asset-curator", {**base, "sections": sections, "candidates": cand, "max_per_section": 2}, report_id=rid)
    n = 0
    with ctx.db.session() as s:
        for ch in out["chosen"]:
            a = s.get(Asset, ch["asset_id"])
            if a and a.user_choice != "skip":
                a.section_key, a.chosen, a.score, a.caption = ch["section_key"], True, ch["score"], ch["caption"] or a.caption
                n += 1
        for a in s.query(Asset).filter_by(report_id=rid, user_choice="use").all():  # the user's choice stands even if the curator passed
            if not a.section_key and sections:
                hint = (a.section_hints or [None])[0]
                a.section_key = hint if hint in {x["key"] for x in sections} else sections[0]["key"]
            a.chosen = True
    return n


def slide_assets(s, rid: str, section_key: str) -> list[Asset]:
    """The chosen assets of a section that a slide can show as they are (a chart that is redrawn natively is not pasted as a picture)."""
    out = []
    for a in s.query(Asset).filter_by(report_id=rid, section_key=section_key, chosen=True).all():
        if a.user_choice == "skip" or a.kind == "chart" or (a.kind == "image" and not a.key):
            continue
        if a.kind == "image" and a.treatment == "redraw" and a.chart and a.user_choice != "use":
            continue
        out.append(a)
    return out


# --------------------------------------------------------------------------- library (for the UI)
def library(ctx: Context, rid: str) -> list[dict]:
    with ctx.db.session() as s:
        srcs = {x.id: x.title for x in s.query(Source).filter_by(report_id=rid).all()}
        used: dict[str, list[int]] = {}
        for sl in s.query(Slide).filter_by(report_id=rid).all():
            for aid in (sl.asset_ids or []):
                used.setdefault(aid, []).append(sl.position + 1)
        rows = s.query(Asset).filter_by(report_id=rid).order_by(Asset.id).all()
        return [{"id": a.id, "kind": a.kind, "role": a.role, "caption": a.caption, "description": a.description, "treatment": a.treatment, "origin": a.origin, "rights": a.rights,
                 "width": a.width, "height": a.height, "section_key": a.section_key, "chosen": a.chosen, "user_choice": a.user_choice, "source": srcs.get(a.source_id, ""),
                 "locator": a.locator, "has_data": bool(a.chart), "chart": a.chart if a.chart else None, "table": a.table[:6] if a.table else None, "parent_id": a.parent_id,
                 "legibility": a.legibility, "analysed": bool(a.analysed), "used_on": sorted(used.get(a.id, [])), "has_image": bool(a.key)} for a in rows]


def patch(ctx: Context, rid: str, aid: str, data: dict) -> dict:
    from .ctx import NotFound

    with ctx.db.session() as s:
        a = s.get(Asset, aid)
        if not a or a.report_id != rid:
            raise NotFound(aid)
        if "user_choice" in data:
            uc = data["user_choice"]
            if uc not in (None, "use", "skip"):
                raise ValueError("user_choice must be use, skip or null")
            a.user_choice = uc
            if uc == "skip":
                a.chosen = False
            elif uc == "use":
                a.chosen = True
                if a.treatment == "discard":
                    a.treatment = "use"
        if data.get("section_key") is not None:
            a.section_key = data["section_key"] or None
        if data.get("caption") is not None:
            a.caption = str(data["caption"])[:300]
        log_event(s, rid, "asset_changed", asset=aid, user_choice=a.user_choice, section=a.section_key)
    return {"ok": True}
