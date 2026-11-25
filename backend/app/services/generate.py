"""Stage 3: slides from approved claims, the PowerPoint file, versions and the 'changes since previous version' list."""
from __future__ import annotations

import copy
from concurrent.futures import ThreadPoolExecutor

from ..core.slides import normalise, numbers_not_in, scrub
from ..models import Asset, Calculation, Claim, Deck, Flag, SectionDraft, Slide
from .ctx import Context, claim_payload, current_claims, draft_of, get_report, log_event, outline, set_state
from .jobs import Progress
from .numbers import allowed_numbers, section_numbers
from .slides import Ledger, build_deck_file, finish, legacy, put


def _t(lang: str, de: str, en: str) -> str:
    return de if lang == "de" else en


def run_generate(ctx: Context, rid: str, prog: Progress, only: list[str] | None = None, instructions: dict[str, str] | None = None) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        set_state(s, r, "GENERATING")
        ver, lang = r.version_no, r.lang
        base = {"lang": lang, "topic": r.topic or r.title, "committee": r.committee or None}
        led = Ledger(s, rid, ver)
        have = {x.section_key for x in s.query(Slide).filter_by(report_id=rid, version_no=ver).all()}
        all_secs = outline(s, rid)
        secs = [o for o in all_secs if (o.key in only if only else o.key not in have)]
        approved = {o.key: current_claims(s, rid, ver, o.key, ("approved",)) for o in all_secs}
        drafts = {o.key: draft_of(s, rid, o.key, ver) for o in all_secs}
        arch_in = {**base, "decision_requested": r.decision_requested or "", "description": r.description or "",
                   "sections": [{"key": o.key, "title": o.title, "headline": drafts[o.key].headline if drafts[o.key] else "", "claims": [claim_payload(c) for c in approved[o.key]],
                                 "open_points": drafts[o.key].open_points if drafts[o.key] else []} for o in all_secs if approved[o.key]],
                   "numbers": [n for o in all_secs for n in section_numbers(approved[o.key], led.ev, led.calcs, lang, 8)][:24],
                   "challenges": [f.text[:200] for f in s.query(Flag).filter_by(report_id=rid, version_no=ver, origin="red_team", status="open").limit(8).all()]}
        work = []
        for o in secs:
            claims = approved[o.key]
            if not claims:
                continue
            d = drafts[o.key]
            assets = s.query(Asset).filter_by(report_id=rid, section_key=o.key, chosen=True).all()
            prev = [x.spec for x in s.query(Slide).filter_by(report_id=rid, version_no=ver, section_key=o.key).order_by(Slide.position).all() if x.spec]
            work.append({"key": o.key, "title": o.title, "claims": claims, "numbers": section_numbers(claims, led.ev, led.calcs, lang),
                         "allowed": allowed_numbers(claims, led.ev, led.calcs),
                         "payload": {**base, "section": {"key": o.key, "title": o.title, "layout": o.layout, "suggested_slides": o.suggested_slides, "headline": d.headline if d else "",
                                                         "claims": [claim_payload(c) for c in claims], "charts": d.charts if d else [], "open_points": d.open_points if d else [],
                                                         "assets": [{"id": a.id, "kind": a.kind, "caption": a.caption, "table": a.table} for a in assets]},
                                     "instruction": (instructions or {}).get(o.key), "previous_slides": prev if (instructions or {}).get(o.key) else []}})
        keep_summary = {x.section_key: x for x in s.query(Slide).filter_by(report_id=rid, version_no=ver).all() if x.section_key in ("_summary", "_decision") and x.user_edited}
        all_claims = [c for o in all_secs for c in approved[o.key]]
        all_allowed = allowed_numbers(all_claims, led.ev, led.calcs)
    steps = len(work) + 3
    prog.update("storyline", 0, steps, "Storyline planen")
    story = ctx.runner.run("storyline-architect", arch_in, report_id=rid)
    per = story.get("slides_per_section", {})

    def write(w):
        payload = {**w["payload"], "numbers": w["numbers"], "storyline": {"deck_title": story.get("deck_title", ""), "summary_title": story["summary"]["title"] if story.get("summary") else "",
                                                                          "index": 1, "count": len(work), "slides": per.get(w["key"], w["payload"]["section"]["suggested_slides"] or 1)}}
        return w["key"], write_section(ctx, rid, payload, w["allowed"], lang)

    prog.update("writing slides", 1, steps, f"{len(work)} Abschnitte")
    done = [1]
    results: dict[str, list[dict]] = {}

    def run_one(w):
        out = write(w)
        done[0] += 1
        prog.update("writing slides", done[0], steps, f"Abschnitt „{w['title']}“ fertig")
        return out
    with ThreadPoolExecutor(max_workers=max(1, ctx.settings.parallel_sections)) as pool:
        for key, specs in pool.map(run_one, work):
            results[key] = specs

    with ctx.db.session() as s:
        led = Ledger(s, rid, ver)
        for key, specs in results.items():
            for x in s.query(Slide).filter_by(report_id=rid, version_no=ver, section_key=key).all():
                s.delete(x)
            s.flush()
            for pos, sp in enumerate(specs):
                sp, _ = finish(led, sp, lang)
                put(s, rid, ver, key, pos, sp)
        for key, name in (("_summary", "summary"), ("_decision", "decision")):
            if key in keep_summary:
                continue
            for x in s.query(Slide).filter_by(report_id=rid, version_no=ver, section_key=key).all():
                s.delete(x)
            s.flush()
            raw = story.get(name)
            if raw:
                sp, _ = normalise({**raw, "kind": "summary" if name == "summary" else "decision"}, lang)
                sp, removed = scrub(sp, all_allowed, lang)
                if sp["blocks"]:
                    sp, _ = finish(led, {**sp, "kind": "summary" if name == "summary" else "decision"}, lang)
                    put(s, rid, ver, key, 0, sp)
        d = s.query(Deck).filter_by(report_id=rid, version_no=ver).first()
        if d:
            d.storyline = {"deck_title": story.get("deck_title"), "slides_per_section": per}
    prog.update("building file", steps - 1, steps, "PowerPoint erstellen")
    build_deck_file(ctx, rid)
    with ctx.db.session() as s:
        d = s.query(Deck).filter_by(report_id=rid, version_no=ver).first()
        if d:
            d.storyline = {"deck_title": story.get("deck_title"), "slides_per_section": per}
        r = get_report(s, rid)
        set_state(s, r, "DECK_REVIEW")
        log_event(s, rid, "deck_generated", version=ver)
    prog.update("done", steps, steps)


def write_section(ctx: Context, rid: str, payload: dict, allowed: list[float], lang: str) -> list[dict]:
    """The slides of one section: written by the slide-writer, every number checked against the ledger; one repair round, then scrubbing."""
    def check(out: dict):
        specs, issues = [], []
        for i, sl in enumerate(out["slides"]):
            sp, _ = normalise(sl, lang)
            bad = numbers_not_in(sp, allowed)
            specs.append(sp)
            if bad:
                issues.append({"slide": i, "message": _t(lang, f"Die Zahl(en) {', '.join(bad)} stehen nicht in den belegten Aussagen oder Berechnungen. Entferne sie oder nimm nur Zahlen aus 'numbers'.",
                                                         f"The number(s) {', '.join(bad)} are not in the verified claims or calculations. Remove them or use only numbers from 'numbers'.")})
        return specs, issues
    out = ctx.runner.run("slide-writer", payload, report_id=rid)
    specs, issues = check(out)
    if issues:
        out = ctx.runner.run("slide-writer", {**payload, "previous_slides": out["slides"], "issues": issues}, report_id=rid)
        specs, issues = check(out)
    final = []
    for sp in specs:
        sp, _ = scrub(sp, allowed, lang)
        if sp["blocks"]:
            final.append(sp)
    return final


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


def _remap_spec(spec: dict, cmap: dict[str, str], calc_map: dict[str, str]) -> dict | None:
    """A slide of the earlier version for the new one: its claim and calculation ids point to the carried copies. Content whose claims are gone is dropped."""
    spec = copy.deepcopy(spec)
    blocks = []
    for b in spec["blocks"]:
        if b["type"] in ("bullets", "kpis"):
            items = []
            for it in b["items"]:
                had = bool(it.get("claim_ids") or it.get("calc_ids"))
                it["claim_ids"] = [cmap[i] for i in it.get("claim_ids", []) if i in cmap]
                it["calc_ids"] = [calc_map[i] for i in it.get("calc_ids", []) if i in calc_map]
                if it["claim_ids"] or it["calc_ids"] or not had:
                    items.append(it)
            if items:
                blocks.append({**b, "items": items})
        else:
            had = bool(b.get("claim_ids") or b.get("calc_ids"))
            b["claim_ids"] = [cmap[i] for i in b.get("claim_ids", []) if i in cmap]
            b["calc_ids"] = [calc_map[i] for i in b.get("calc_ids", []) if i in calc_map]
            if b["claim_ids"] or b["calc_ids"] or not had:
                blocks.append(b)
    if not blocks and spec.get("kind") not in ("title",):
        return None
    spec["blocks"] = blocks
    return spec


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
            if sl.section_key in ("_sources", "_changes"):
                continue  # recomputed
            spec = _remap_spec(sl.spec, cmap, calc_map) if sl.spec else None
            if spec is None:
                continue
            bullets, chart, assets = legacy(spec)
            s.add(Slide(report_id=rid, version_no=new, section_key=sl.section_key, position=sl.position, title=sl.title, bullets=bullets, chart=chart or sl.chart,
                        asset_ids=assets, notes=sl.notes, layout=sl.layout, spec=spec, kind=sl.kind, history=[], user_edited=sl.user_edited))
        log_event(s, rid, "new_version", **{"from": old, "to": new})
        return new
