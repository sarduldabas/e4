"""Stage 3: slides from approved claims, the PowerPoint file, versions and the 'changes since previous version' list."""
from __future__ import annotations

import copy

from ..core.deck import SlideSpec, build_deck
from ..models import Asset, Calculation, Claim, Deck, Evidence, FileRow, Report, SectionDraft, Slide, Source
from .ctx import Context, claim_payload, current_claims, draft_of, get_report, log_event, outline, set_state
from .jobs import Progress


def _t(lang: str, de: str, en: str) -> str:
    return de if lang == "de" else en


def run_generate(ctx: Context, rid: str, prog: Progress, only: list[str] | None = None, instructions: dict[str, str] | None = None) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        set_state(s, r, "GENERATING")
        ver, lang = r.version_no, r.lang
        base = {"lang": lang, "topic": r.topic or r.title, "committee": r.committee or None}
        have = {x.section_key for x in s.query(Slide).filter_by(report_id=rid, version_no=ver).all()}
        secs = [o for o in outline(s, rid) if (o.key in only if only else o.key not in have)]
        todo = []
        for o in secs:
            claims = current_claims(s, rid, ver, o.key, ("approved",))
            if not claims:
                continue
            d = draft_of(s, rid, o.key, ver)
            assets = s.query(Asset).filter_by(report_id=rid, section_key=o.key, chosen=True).all()
            prev = [{"title": x.title, "bullets": x.bullets, "chart_id": (x.chart or {}).get("id"), "asset_ids": x.asset_ids, "notes": x.notes, "layout": x.layout}
                    for x in s.query(Slide).filter_by(report_id=rid, version_no=ver, section_key=o.key).order_by(Slide.position).all()]
            todo.append({"key": o.key, "payload": {**base, "section": {"key": o.key, "title": o.title, "layout": o.layout, "suggested_slides": o.suggested_slides,
                         "headline": d.headline if d else "", "claims": [claim_payload(c) for c in claims], "charts": d.charts if d else [],
                         "assets": [{"id": a.id, "kind": a.kind, "caption": a.caption} for a in assets]},
                         "instruction": (instructions or {}).get(o.key), "previous_slides": prev if (instructions or {}).get(o.key) else []},
                         "charts": {c["id"]: c for c in (d.charts if d else [])}})
    prog.update("writing slides", 0, len(todo) + 1, f"{len(todo)} Abschnitte")
    for n, t in enumerate(todo, 1):
        out = ctx.runner.run("slide-writer", t["payload"], report_id=rid)
        with ctx.db.session() as s:
            for x in s.query(Slide).filter_by(report_id=rid, version_no=ver, section_key=t["key"]).all():
                s.delete(x)
            s.flush()
            for pos, sl in enumerate(out["slides"]):
                ch = t["charts"].get(sl.get("chart_id"))
                s.add(Slide(report_id=rid, version_no=ver, section_key=t["key"], position=pos, title=sl["title"], bullets=sl["bullets"],
                            chart={k: v for k, v in ch.items() if k in ("id", "type", "title", "unit", "labels", "values")} if ch else None,
                            asset_ids=sl["asset_ids"], notes=sl["notes"], layout=sl.get("layout")))
        prog.update("writing slides", n, len(todo) + 1)
    prog.update("building file", len(todo), len(todo) + 1, "PowerPoint erstellen")
    build_deck_file(ctx, rid)
    with ctx.db.session() as s:
        r = get_report(s, rid)
        set_state(s, r, "DECK_REVIEW")
        log_event(s, rid, "deck_generated", version=ver)
    prog.update("done", len(todo) + 1, len(todo) + 1)


def build_deck_file(ctx: Context, rid: str) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        ver, lang = r.version_no, r.lang
        order = {o.key: o.position for o in outline(s, rid)}
        slides = [x for x in s.query(Slide).filter_by(report_id=rid, version_no=ver).all() if x.section_key in order]
        slides.sort(key=lambda x: (order[x.section_key], x.position))
        claims = {c.id: c for c in s.query(Claim).filter_by(report_id=rid, version_no=ver).all()}
        ev = {e.id: e for e in s.query(Evidence).filter_by(report_id=rid).all()}
        srcs = {x.id: x for x in s.query(Source).filter_by(report_id=rid).all()}
        assets = {a.id: a for a in s.query(Asset).filter_by(report_id=rid).all()}
        tpl = s.query(FileRow).filter_by(report_id=rid, role="template").order_by(FileRow.created_at.desc()).first()
        tpl_bytes = ctx.store.get(tpl.key) if tpl else None
        used: dict[str, set[str]] = {}
        specs: list[SlideSpec] = []

        def sources_of(claim_ids: list[str]) -> list[tuple[str, str]]:
            out: list[tuple[str, str]] = []
            for cid in claim_ids:
                c = claims.get(cid)
                for eid in (c.evidence_ids if c else []):
                    e = ev.get(eid)
                    if not e:
                        continue
                    label = _t(lang, "Angabe des Autors", "Author's input") if e.origin == "user" else (srcs[e.source_id].title if e.source_id in srcs else "")
                    if label and (label, e.locator) not in out:
                        out.append((label, e.locator))
            return out

        for sl in slides:
            cids = [cid for b in sl.bullets for cid in b.get("claim_ids", [])]
            refs = sources_of(cids)
            for label, loc in refs:
                used.setdefault(label, set()).add(loc)
            notes = sl.notes or ""
            lines = []
            for cid in dict.fromkeys(cids):
                c = claims.get(cid)
                for eid in (c.evidence_ids if c else [])[:3]:
                    e = ev.get(eid)
                    if e:
                        src = _t(lang, "Angabe des Autors", "Author's input") if e.origin == "user" else (srcs[e.source_id].title if e.source_id in srcs else "")
                        lines.append(f"- {e.statement} [{src}{', ' + e.locator if e.locator else ''}]")
            if lines:
                notes += ("\n\n" + _t(lang, "Belege:", "Evidence:") + "\n" + "\n".join(dict.fromkeys(lines)))
            imgs, table = [], None
            for aid in sl.asset_ids:
                a = assets.get(aid)
                if not a:
                    continue
                if a.kind == "image" and a.key:
                    imgs.append((ctx.store.get(a.key), a.caption))
                elif a.kind == "table" and a.table and table is None:
                    table = a.table[:8]
            specs.append(SlideSpec(title=sl.title, bullets=[b["text"] for b in sl.bullets], notes=notes, layout=sl.layout, chart=sl.chart,
                                   images=imgs[:1], table=None if sl.chart or imgs else table,
                                   footer=(_t(lang, "Quellen: ", "Sources: ") + "; ".join(f"{a}{' (' + b + ')' if b else ''}" for a, b in refs[:3]) + (" …" if len(refs) > 3 else "")) if refs else ""))
        changes = diff_versions(s, rid, ver, lang) if ver > 1 else []
        if used:
            specs.append(SlideSpec(title=_t(lang, "Quellen", "Sources"), bullets=[f"{k} ({', '.join(sorted(v - {''}))})" if v - {""} else k for k, v in sorted(used.items())][:12]))
        if ver > 1:
            specs.append(SlideSpec(title=_t(lang, f"Änderungen gegenüber v{ver - 1}", f"Changes since v{ver - 1}"), bullets=(changes or [_t(lang, "Keine inhaltlichen Änderungen.", "No changes in content.")])[:10]))
        date = ".".join(reversed(r.date.split("-"))) if lang == "de" and len(r.date) == 10 and r.date[4] == "-" else r.date
        subtitle = " · ".join(x for x in [r.committee, date, r.version] if x)
        title = r.title
    data = build_deck(specs, template=tpl_bytes, title=title, subtitle=subtitle, lang=lang)
    key = f"reports/{rid}/decks/v{ver}.pptx"
    ctx.store.put(key, data)
    with ctx.db.session() as s:
        for d in s.query(Deck).filter_by(report_id=rid, version_no=ver).all():
            s.delete(d)
        s.flush()
        s.add(Deck(report_id=rid, version_no=ver, key=key, slide_count=len(specs) + 1, changes=changes))
    return {"key": key, "slides": len(specs) + 1, "changes": changes}


def diff_versions(s, rid: str, ver: int, lang: str) -> list[str]:
    titles = {o.key: o.title for o in outline(s, rid)}
    new = current_claims(s, rid, ver, None, ("approved",))
    old = current_claims(s, rid, ver - 1, None, ("approved",))
    carried = {c.carried_from for c in new if c.carried_from}
    lines: list[str] = []
    for c in new:
        if not c.carried_from:
            lines.append(f"{titles.get(c.section_key, c.section_key)}: {_t(lang, 'neu', 'new')} – {c.text[:110]}")
    for c in old:
        if c.id not in carried:
            lines.append(f"{titles.get(c.section_key, c.section_key)}: {_t(lang, 'entfernt', 'removed')} – {c.text[:110]}")
    return lines


def new_version(ctx: Context, rid: str) -> int:
    """v2 starts as a copy of v1: approved claims (with their calculations), drafts and slides are carried forward."""
    with ctx.db.session() as s:
        r = get_report(s, rid)
        old, new = r.version_no, r.version_no + 1
        r.version_no, r.version = new, f"v{new}"
        cmap: dict[str, str] = {}
        calc_map: dict[str, str] = {}
        for c in current_claims(s, rid, old, None, ("approved",)):
            for cid in c.calc_ids:
                if cid not in calc_map:
                    k = s.get(Calculation, cid)
                    nk = Calculation(report_id=rid, section_key=k.section_key, ref=k.ref, label=k.label, formula=k.formula, inputs=k.inputs, value=k.value, unit=k.unit, error=k.error, version_no=new)
                    s.add(nk)
                    s.flush()
                    calc_map[cid] = nk.id
            nc = Claim(report_id=rid, section_key=c.section_key, ref=c.ref, position=c.position, text=c.text, kind=c.kind, evidence_ids=list(c.evidence_ids),
                       calc_ids=[calc_map[i] for i in c.calc_ids if i in calc_map], confidence=c.confidence, status="approved", verdict=c.verdict, issues=[],
                       user_edited=c.user_edited, version_no=new, carried_from=c.id)
            s.add(nc)
            s.flush()
            cmap[c.id] = nc.id
        for d in s.query(SectionDraft).filter_by(report_id=rid, version_no=old).all():
            charts = copy.deepcopy(d.charts)
            for ch in charts:
                ch["calc_ids"] = [calc_map.get(i, i) for i in ch.get("calc_ids", [])]
                ch["claim_ids"] = [cmap[i] for i in ch.get("claim_ids", []) if i in cmap]
            s.add(SectionDraft(report_id=rid, section_key=d.section_key, version_no=new, headline=d.headline, charts=charts, open_points=d.open_points, rounds=d.rounds, verified=True))
        for sl in s.query(Slide).filter_by(report_id=rid, version_no=old).all():
            bullets = [{**b, "claim_ids": [cmap[i] for i in b.get("claim_ids", []) if i in cmap]} for b in sl.bullets]
            bullets = [b for b in bullets if b["claim_ids"]]
            if bullets:
                s.add(Slide(report_id=rid, version_no=new, section_key=sl.section_key, position=sl.position, title=sl.title, bullets=bullets, chart=sl.chart,
                            asset_ids=sl.asset_ids, notes=sl.notes, layout=sl.layout, user_edited=sl.user_edited))
        log_event(s, rid, "new_version", **{"from": old, "to": new})
        return new
