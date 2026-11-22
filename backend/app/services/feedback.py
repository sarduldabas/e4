"""Feedback on the finished deck: interpret it, start version 2, and re-run only what the feedback touches."""
from __future__ import annotations

from ..models import Claim, Feedback, Slide
from .analyse import run_analyse
from .collect import run_collect
from .ctx import Context, StateError, current_claims, get_report, log_event, outline, require_state, set_state
from .generate import build_deck_file, new_version, run_generate
from .jobs import Progress

ORDER = {"slides": 0, "analysis": 1, "collection": 2}


def interpret(ctx: Context, rid: str, text: str, selected_slide_id: str | None) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW", "FINAL")
        order = {o.key: o.position for o in outline(s, rid)}
        slides = sorted(s.query(Slide).filter_by(report_id=rid, version_no=r.version_no).all(), key=lambda x: (order.get(x.section_key, 99), x.position))
        payload = {"lang": r.lang, "feedback": text, "selected_slide_id": selected_slide_id,
                   "slides": [{"id": x.id, "index": i + 2, "section_key": x.section_key, "title": x.title, "claim_ids": [c for b in x.bullets for c in b.get("claim_ids", [])]} for i, x in enumerate(slides)],
                   "sections": [[o.key, o.title] for o in outline(s, rid)]}
    out = ctx.runner.run("feedback-interpreter", payload, report_id=rid)
    with ctx.db.session() as s:
        r = get_report(s, rid)
        fb = Feedback(report_id=rid, text=text, selected_slide_id=selected_slide_id, interpreted=out, status="planned" if out["changes"] else "new", version_no=r.version_no)
        s.add(fb)
        s.flush()
        log_event(s, rid, "feedback", changes=len(out["changes"]), clarification=bool(out.get("clarification")))
        return {"id": fb.id, **out}


def plan_of(changes: list[dict]) -> dict:
    col, ana, sl, manual, skipped = {}, {}, {}, [], []
    for c in changes:
        sec = c.get("section_key")
        if c["action"] == "reorder":
            manual.append(c)
            continue
        if not sec:
            skipped.append(c)
            continue
        target = {"collection": col, "analysis": ana, "slides": sl}[c["rerun_from"]]
        target[sec] = (target.get(sec, "") + " " + c["instruction"]).strip()
    for k in list(ana):
        if k in col:
            del ana[k]
    for k in list(sl):
        if k in col or k in ana:
            sl.pop(k)
    return {"collect": col, "analyse": ana, "slides": sl, "manual": manual, "skipped": skipped}


def run_feedback(ctx: Context, rid: str, prog: Progress, feedback_id: str) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW", "FINAL")
        fb = s.get(Feedback, feedback_id)
        if not fb or not fb.interpreted["changes"]:
            raise StateError("there is nothing to apply")
        plan = plan_of(fb.interpreted["changes"])
    ver = new_version(ctx, rid)
    with ctx.db.session() as s:
        r = get_report(s, rid)
        r.state, r.stage = "FEEDBACK", 3
        fb = s.get(Feedback, feedback_id)
        fb.version_no, fb.status = ver, "applied"
        fb.interpreted = {**fb.interpreted, "plan": {k: v for k, v in plan.items()}}
        log_event(s, rid, "feedback_applied", version=ver, collect=list(plan["collect"]), analyse=list(plan["analyse"]), slides=list(plan["slides"]))
        # sections that must be re-analysed lose their carried claims and slides; the rest keeps v1's approved content
        for key in {*plan["collect"], *plan["analyse"]}:
            for c in current_claims(s, rid, ver, key):
                s.delete(c)
            for x in s.query(Slide).filter_by(report_id=rid, version_no=ver, section_key=key).all():
                s.delete(x)
    if plan["collect"]:
        run_collect(ctx, rid, prog, only=list(plan["collect"]))
    if plan["collect"] or plan["analyse"]:
        keys = list({*plan["collect"], *plan["analyse"]})
        instr = {**plan["analyse"], **plan["collect"]}
        run_analyse(ctx, rid, prog, only=keys, instructions=instr)  # ends in FINDINGS_REVIEW: the user approves the new claims
        if plan["slides"]:
            with ctx.db.session() as s:
                for key in plan["slides"]:  # slide-only changes are applied when the deck is generated again
                    for x in s.query(Slide).filter_by(report_id=rid, version_no=ver, section_key=key).all():
                        s.delete(x)
        return
    with ctx.db.session() as s:
        set_state(s, get_report(s, rid), "GENERATING")
    run_generate(ctx, rid, prog, only=list(plan["slides"]), instructions=plan["slides"])


def pending_instructions(ctx: Context, rid: str) -> dict[str, str]:
    """Wording instructions from the feedback of the current version, applied when slides are generated again."""
    with ctx.db.session() as s:
        r = get_report(s, rid)
        out: dict[str, str] = {}
        for fb in s.query(Feedback).filter_by(report_id=rid, version_no=r.version_no, status="applied").all():
            for c in (fb.interpreted or {}).get("changes", []):
                if c.get("section_key") and c["action"] != "reorder":
                    out[c["section_key"]] = (out.get(c["section_key"], "") + " " + c["instruction"]).strip()
        return out
