"""Stage 3: slides from approved claims, the PowerPoint file, versions and the 'changes since previous version' list."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from ..core.slides import normalise, numbers_not_in, scrub
from . import assets as assets_svc
from ..models import Asset, Claim, Deck, Flag, SectionDraft, Slide
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
            assets = assets_svc.slide_assets(s, rid, o.key)
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


def auto_approve(ctx: Context, rid: str, only: list[str] | None = None) -> int:
    """There is no approval step: what the verifier supports goes into the deck. A claim it flagged stays out and is listed as something to look at;
    the author can take it in with one click. Returns the number of claims that are in."""
    with ctx.db.session() as s:
        r = get_report(s, rid)
        n = 0
        for c in current_claims(s, rid, r.version_no, None, ("verified", "approved")):
            if only and c.section_key not in only:
                continue
            if c.status != "approved":
                c.status = "approved"
            n += 1
        total = s.query(Claim).filter_by(report_id=rid, version_no=r.version_no, status="approved").count()
        if not total:
            raise ValueError("no finding could be verified against the sources, so there is nothing to build slides from; add material or a link and run the research again")
        log_event(s, rid, "claims_taken_in", claims=n, sections=only or "all")
        return n
