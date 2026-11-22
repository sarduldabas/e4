"""Stage 1: outline from the template, and the interview."""
from __future__ import annotations

import re
import unicodedata

from ..core.parsers import read_template
from ..models import Evidence, FileRow, InterviewTurn, OutlineSection, Source
from .ctx import Context, StateError, get_report, log_event, outline, require_state, set_state


def slugify(text: str) -> str:
    t = text.lower().replace("ß", "ss").replace("ä", "ae").replace("ö", "oe").replace("ü", "ue")
    s = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40] or "section"


def section_view(o: OutlineSection) -> dict:
    return {"key": o.key, "title": o.title, "purpose": o.purpose, "layout": o.layout, "required_inputs": o.required_inputs,
            "suggested_slides": o.suggested_slides, "origin": o.origin, "included": o.included, "position": o.position}


def propose_outline(ctx: Context, rid: str) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "SETUP", "OUTLINE_REVIEW")
        tpl = s.query(FileRow).filter_by(report_id=rid, role="template").order_by(FileRow.created_at.desc()).first()
        payload = {"lang": r.lang, "topic": r.topic or r.title, "description": r.description, "committee": r.committee or None}
        note = None
        if tpl:
            try:
                payload["template"] = read_template(ctx.store.get(tpl.key), tpl.name)
            except Exception as e:  # noqa: BLE001
                note = f"template could not be read ({e.__class__.__name__}): standard outline proposed"
    out = ctx.runner.run("template-analyst", payload, report_id=rid)
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "SETUP", "OUTLINE_REVIEW")
        for o in s.query(OutlineSection).filter_by(report_id=rid, origin="agent").all():
            s.delete(o)
        s.flush()
        kept = {o.key for o in s.query(OutlineSection).filter_by(report_id=rid).all()}
        pos = max([o.position for o in s.query(OutlineSection).filter_by(report_id=rid).all()] + [-1]) + 1
        for sec in out["sections"]:
            if sec["key"] in kept:
                continue
            s.add(OutlineSection(report_id=rid, key=sec["key"], position=pos, title=sec["title"], purpose=sec.get("purpose", ""), layout=sec.get("layout"),
                                 required_inputs=sec.get("required_inputs", []), suggested_slides=sec.get("suggested_slides", 1), origin="agent"))
            pos += 1
        set_state(s, r, "OUTLINE_REVIEW")
        log_event(s, rid, "outline_proposed", sections=len(out["sections"]))
        s.flush()
        return {"sections": [section_view(o) for o in outline(s, rid, False)], "notes": note or out.get("notes")}


def get_outline(ctx: Context, rid: str) -> list[dict]:
    with ctx.db.session() as s:
        get_report(s, rid)
        return [section_view(o) for o in outline(s, rid, False)]


def update_outline(ctx: Context, rid: str, sections: list[dict]) -> list[dict]:
    """The user's edited outline replaces the old one (order, titles, purposes, removed or added sections)."""
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "SETUP", "OUTLINE_REVIEW", "COLLECTING")
        old = {o.key: o for o in s.query(OutlineSection).filter_by(report_id=rid).all()}
        seen: set[str] = set()
        for pos, sec in enumerate(sections):
            title = (sec.get("title") or "").strip()
            if not title:
                continue
            key = sec.get("key") if sec.get("key") in old else slugify(title)
            while key in seen:
                key += "-2"
            seen.add(key)
            row = old.get(key)
            if not row:
                row = OutlineSection(report_id=rid, key=key, origin="user")
                s.add(row)
            edited = row.title != title or row.purpose != sec.get("purpose", row.purpose)
            row.position, row.title = pos, title
            row.purpose = sec.get("purpose", row.purpose or "")
            row.layout = sec.get("layout", row.layout)
            row.required_inputs = sec.get("required_inputs", row.required_inputs or [])
            row.suggested_slides = max(1, min(int(sec.get("suggested_slides", row.suggested_slides or 1)), 4))
            row.included = bool(sec.get("included", True))
            if edited and row.origin == "agent":
                row.origin = "user"
        for k, row in old.items():
            if k not in seen:
                row.included = False  # kept in the ledger, out of the report
        log_event(s, rid, "outline_edited", sections=len(seen))
        s.flush()
        return [section_view(o) for o in outline(s, rid, False)]


# ---------------------------------------------------------------- interview
def interview_turn(ctx: Context, rid: str, text: str = "", done: bool = False) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "OUTLINE_REVIEW", "COLLECTING")
        secs = outline(s, rid)
        if not secs:
            raise StateError("propose the outline first")
        turns = s.query(InterviewTurn).filter_by(report_id=rid).order_by(InterviewTurn.created_at, InterviewTurn.id).all()
        known = [{"label": e.kind, "statement": e.statement, "section_key": e.section_key}
                 for e in s.query(Evidence).filter(Evidence.report_id == rid, Evidence.origin != "user", Evidence.status == "active").limit(60).all()]
        payload = {"lang": r.lang, "topic": r.topic or r.title, "description": r.description,
                   "sections": [{"key": o.key, "title": o.title, "required_inputs": o.required_inputs} for o in secs],
                   "turns": [{"role": t.role, "text": t.text} for t in turns], "user_text": text.strip(), "known_evidence": known,
                   "questions_asked": sum(1 for t in turns if t.role == "agent"), "user_done": done}
    out = ctx.runner.run("interviewer", payload, report_id=rid)
    with ctx.db.session() as s:
        if text.strip():
            s.add(InterviewTurn(report_id=rid, role="user", text=text.strip()))
        for st in out["statements"]:
            s.add(Evidence(report_id=rid, section_key=st.get("section_key") or "_general", origin="user", kind={"decision": "decision", "risk": "risk", "number": "number"}.get(st["kind"], "fact"),
                           statement=st["statement"], quote=st["statement"], locator="Interview", value=st.get("value"), unit=st.get("unit"), confidence=0.9))
        nq = out.get("next_question")
        if nq and not out["done"]:
            s.add(InterviewTurn(report_id=rid, role="agent", text=nq["text"], section_key=nq.get("section_key")))
        log_event(s, rid, "interview_turn", statements=len(out["statements"]), done=out["done"], reason=out.get("done_reason"))
    return out


def get_interview(ctx: Context, rid: str) -> dict:
    with ctx.db.session() as s:
        get_report(s, rid)
        turns = s.query(InterviewTurn).filter_by(report_id=rid).order_by(InterviewTurn.created_at, InterviewTurn.id).all()
        ev = s.query(Evidence).filter_by(report_id=rid, origin="user").order_by(Evidence.created_at).all()
        return {"turns": [{"role": t.role, "text": t.text, "section_key": t.section_key} for t in turns],
                "statements": [{"id": e.id, "section_key": e.section_key, "kind": e.kind, "statement": e.statement, "value": e.value, "unit": e.unit} for e in ev]}
