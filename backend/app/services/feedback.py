"""Ask AI: a request in plain words about one slide, one section or the whole deck, carried out in place.

One slide is changed by the slide-editor (services/slides.py). A section or the whole deck goes through the feedback-interpreter, which says per section
whether the wording, the analysis or the research has to run again; those parts are run again and the slides of the sections are written anew.
What is replaced is saved first (a snapshot), so the last such change can be undone with one click. There are no versions and no approval steps."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, inspect as sa_inspect

from ..models import Calculation, Claim, DeckSnapshot, Feedback, SectionDraft, Slide
from . import slides as slides_service
from .analyse import run_analyse
from .collect import run_collect
from .ctx import Context, StateError, get_report, log_event, outline, require_state
from .generate import auto_approve, run_generate
from .jobs import Progress

KEEP_SNAPSHOTS = 5
SNAPSHOT_MODELS = (Slide, Claim, Calculation, SectionDraft)


def _t(lang: str, de: str, en: str) -> str:
    return de if lang == "de" else en


# ---------------------------------------------------------------------------------------------- understanding the request
def interpret(ctx: Context, rid: str, text: str, selected_slide_id: str | None) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW")
        order = {o.key: o.position for o in outline(s, rid)}
        slides = sorted(s.query(Slide).filter_by(report_id=rid, version_no=r.version_no).all(), key=lambda x: (order.get(x.section_key, 99), x.position))
        payload = {"lang": r.lang, "feedback": text, "selected_slide_id": selected_slide_id,
                   "slides": [{"id": x.id, "index": i + 1, "section_key": x.section_key, "title": x.title, "claim_ids": [c for b in x.bullets for c in b.get("claim_ids", [])]} for i, x in enumerate(slides)],
                   "sections": [[o.key, o.title] for o in outline(s, rid)]}
    out = ctx.runner.run("feedback-interpreter", payload, report_id=rid)
    with ctx.db.session() as s:
        r = get_report(s, rid)
        fb = Feedback(report_id=rid, text=text, selected_slide_id=selected_slide_id, interpreted=out, status="planned" if out["changes"] else "new", version_no=r.version_no)
        s.add(fb)
        s.flush()
        log_event(s, rid, "ask_ai", scope="deck", changes=len(out["changes"]), clarification=bool(out.get("clarification")), text=text[:300])
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


def slide_result(res: dict) -> dict:
    """The answer for a change to one slide: `mode` says what kind of answer it is, `agent_mode` whether the language model or the rules made it."""
    return {**{k: v for k, v in res.items() if k != "mode"}, "mode": "slide", "agent_mode": res.get("mode")}


def ask(ctx: Context, rid: str, text: str, scope: str, slide_id: str | None = None, section_key: str | None = None) -> dict:
    """scope: 'slide' | 'section' | 'deck'. A slide is changed at once and the result returned; a section or the deck is changed by a background job."""
    text = (text or "").strip()
    if not text:
        raise ValueError("write what should change")
    if scope not in ("slide", "section", "deck"):
        raise ValueError("scope must be slide, section or deck")
    if scope == "slide":
        if not slide_id:
            raise ValueError("choose a slide")
        with ctx.db.session() as s:
            log_event(s, rid, "ask_ai", scope="slide", slide=slide_id, text=text[:300])
        return slide_result(slides_service.revise_slide(ctx, rid, slide_id, text))
    if scope == "section" and not section_key:
        raise ValueError("choose a section")
    out = interpret(ctx, rid, text, slide_id)
    changes = [{**c, "section_key": c.get("section_key") or (section_key if scope == "section" else None)} for c in out["changes"]]
    plan = plan_of(changes)
    if not (plan["collect"] or plan["analyse"] or plan["slides"]):
        return {"mode": "none", "clarification": out.get("clarification"), "manual": plan["manual"], "skipped": plan["skipped"]}
    with ctx.db.session() as s:
        fb = s.get(Feedback, out["id"])
        fb.interpreted, fb.status = {**(fb.interpreted or {}), "changes": changes, "plan": plan}, "applied"
        titles = {o.key: o.title for o in outline(s, rid)}
        keys = list(dict.fromkeys([*plan["collect"], *plan["analyse"], *plan["slides"]]))
        label = text[:120]
    job = ctx.jobs.submit(rid, "ask", lambda prog: run_ask(ctx, rid, prog, plan, label))
    return {"mode": "job", "job_id": job, "sections": [titles.get(k, k) for k in keys], "rewrites": bool(plan["collect"] or plan["analyse"]), "manual": plan["manual"], "skipped": plan["skipped"]}


# ---------------------------------------------------------------------------------------------- doing it
def run_ask(ctx: Context, rid: str, prog: Progress, plan: dict, label: str) -> None:
    research = {**plan["analyse"], **plan["collect"]}
    keys = list(dict.fromkeys([*plan["collect"], *plan["analyse"], *plan["slides"]]))
    snapshot(ctx, rid, keys, label)
    try:
        if plan["collect"]:
            run_collect(ctx, rid, prog, only=list(plan["collect"]))
        if research:
            run_analyse(ctx, rid, prog, only=list(research), instructions=research)
            auto_approve(ctx, rid, only=list(research))
        run_generate(ctx, rid, prog, only=keys, instructions={**plan["slides"], **research})
    except Exception:
        recover_state(ctx, rid)
        raise


def recover_state(ctx: Context, rid: str) -> None:
    """A step that failed half-way must not leave the draft locked: if there are slides, the report is a draft again."""
    with ctx.db.session() as s:
        r = get_report(s, rid)
        if r.state != "DECK_REVIEW" and s.query(Slide).filter_by(report_id=rid, version_no=r.version_no).count():
            r.state, r.stage = "DECK_REVIEW", 2
            log_event(s, rid, "state", **{"from": "failed step", "to": "DECK_REVIEW"})


# ---------------------------------------------------------------------------------------------- undo of the last section-level change
def _dump(row) -> dict:
    out = {}
    for col in sa_inspect(row).mapper.column_attrs:
        v = getattr(row, col.key)
        out[col.key] = v.isoformat() if isinstance(v, datetime) else v
    return out


def _load(model, data: dict):
    kw = {}
    for col in sa_inspect(model).mapper.column_attrs:
        v = data.get(col.key)
        if isinstance(col.columns[0].type, DateTime) and isinstance(v, str):
            v = datetime.fromisoformat(v)
        kw[col.key] = v
    return model(**kw)


def _scope(keys: list[str]) -> list[str]:
    return list(dict.fromkeys([*keys, "_summary", "_decision"]))  # the summary and the decision slide are written again with the sections


def snapshot(ctx: Context, rid: str, keys: list[str], label: str) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        scope = _scope(keys)
        data = {m.__tablename__: [_dump(x) for x in s.query(m).filter(m.report_id == rid, m.version_no == r.version_no, m.section_key.in_(scope)).all()] for m in SNAPSHOT_MODELS}
        s.add(DeckSnapshot(report_id=rid, label=label, data={"keys": scope, "rows": data}))
        s.flush()
        old = s.query(DeckSnapshot).filter_by(report_id=rid).order_by(DeckSnapshot.created_at.desc()).all()[KEEP_SNAPSHOTS:]
        for o in old:
            s.delete(o)


def undo_ask(ctx: Context, rid: str) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW")
        snap = s.query(DeckSnapshot).filter_by(report_id=rid).order_by(DeckSnapshot.created_at.desc()).first()
        if not snap:
            raise StateError("nothing to undo")
        scope, rows = snap.data["keys"], snap.data["rows"]
        for m in SNAPSHOT_MODELS:
            for x in s.query(m).filter(m.report_id == rid, m.version_no == r.version_no, m.section_key.in_(scope)).all():
                s.delete(x)
        s.flush()
        for m in SNAPSHOT_MODELS:
            for d in rows.get(m.__tablename__, []):
                s.add(_load(m, d))
        label = snap.label
        s.delete(snap)
        log_event(s, rid, "ask_ai_undone", text=label[:300])
    slides_service.build_deck_file(ctx, rid)
    return {"undone": label}
