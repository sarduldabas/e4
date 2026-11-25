"""Stage 2, second half: per section plan -> calculate (code) -> write -> verify, then the red team over the whole draft."""
from __future__ import annotations

import math
from concurrent.futures import ThreadPoolExecutor

from ..core.calc import CalcError, evaluate
from ..models import Calculation, Claim, Evidence, Flag, SectionDraft
from .ctx import (Context, calc_payload, claim_payload, current_claims, draft_of, evidence_refs, get_report, log_event, outline, set_state)
from .jobs import Progress
from .retrieval import Index, load_passages


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)


def run_analyse(ctx: Context, rid: str, prog: Progress, only: list[str] | None = None, instructions: dict[str, str] | None = None) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        set_state(s, r, "ANALYSING")
        ver = r.version_no
        base = {"lang": r.lang, "topic": r.topic or r.title, "committee": r.committee or None, "decision_requested": r.decision_requested or "", "description": r.description or "",
                "outline": [o.title for o in outline(s, rid)]}
        secs = [{"key": o.key, "title": o.title, "purpose": o.purpose, "required_inputs": o.required_inputs} for o in outline(s, rid) if not only or o.key in only]
    index = Index(load_passages(ctx, rid))  # the original text of every source, searchable; each section reads what matters to it
    done = [0]
    prog.update("analysing", 0, len(secs) + 1, f"{len(secs)} Abschnitte analysieren")

    def work(sec: dict):
        try:
            analyse_section(ctx, rid, ver, base, sec, (instructions or {}).get(sec["key"]), index)
        finally:
            done[0] += 1
            prog.update("analysing", done[0], len(secs) + 1, f"Abschnitt „{sec['title']}“ fertig")

    with ThreadPoolExecutor(max_workers=max(1, ctx.settings.parallel_sections)) as pool:
        list(pool.map(work, secs))
    prog.update("red-team", len(secs), len(secs) + 1, "Gesamtentwurf prüfen")
    run_red_team(ctx, rid, ver, base)
    with ctx.db.session() as s:
        r = get_report(s, rid)
        set_state(s, r, "FINDINGS_REVIEW")
        log_event(s, rid, "analysed", sections=len(secs), version=ver)
    prog.update("analysed", len(secs) + 1, len(secs) + 1)


def section_passages(ctx: Context, index: Index | None, base: dict, sec: dict, instruction: str | None) -> list[dict]:
    """The raw text most relevant to one section, up to the budget: what the analyst reads besides the extracted evidence."""
    if not index or not index.passages:
        return []
    query = " ".join([sec["title"], sec.get("purpose", ""), " ".join(sec.get("required_inputs", [])), base.get("topic", ""), instruction or ""])
    return [{"id": p.id, "source": p.source_title, "locator": p.locator, "text": p.text} for p in index.top(query, ctx.settings.passage_chars)]


def analyse_section(ctx: Context, rid: str, ver: int, base: dict, sec: dict, instruction: str | None = None, index: Index | None = None) -> None:
    with ctx.db.session() as s:
        ev = evidence_refs(s, rid, sec["key"], limit=120)
    ev_by_id = {e["id"]: e for e in ev}
    passages = section_passages(ctx, index, base, sec, instruction)
    asec = {"key": sec["key"], "title": sec["title"], "purpose": sec.get("purpose", ""), "required_inputs": sec.get("required_inputs", [])}

    # plan -> calculate in code
    calcs: list[dict] = []
    calc_rows: list[dict] = []
    if any(e["value"] is not None for e in ev):
        plan = ctx.runner.run("section-analyst", {**base, "mode": "plan", "section": asec, "evidence": ev}, report_id=rid)
        for c in plan["calculations"]:
            try:
                vals = {v: float(ev_by_id[eid]["value"]) for v, eid in c["variables"].items()}
                value = evaluate(c["formula"], vals)
                calcs.append({"id": c["id"], "label": c["label"], "formula": c["formula"], "value": value, "unit": c.get("unit"), "inputs": c["variables"]})
                calc_rows.append({**calcs[-1], "error": None})
            except (CalcError, KeyError, TypeError) as e:
                calc_rows.append({"id": c["id"], "label": c["label"], "formula": c["formula"], "value": None, "unit": c.get("unit"), "inputs": c["variables"], "error": str(e)[:180]})

    max_rounds = max(1, ctx.settings.max_analysis_rounds)
    write_in = {**base, "mode": "write", "section": asec, "evidence": ev, "calculations": calcs, "instruction": instruction, "round": 1}
    write_in["passages"] = passages
    draft = ctx.runner.run("section-analyst", write_in, report_id=rid)
    draft = _take_new_evidence(ctx, rid, sec["key"], draft, ev, ev_by_id, passages)
    rounds, check = 1, None
    while True:
        check = ctx.runner.run("verifier", {"lang": base["lang"], "section_key": sec["key"], "section_title": sec["title"], "headline": draft["headline"],
                                            "claims": draft["claims"], "evidence": ev, "calculations": calcs}, report_id=rid)
        problems = [c for c in check["checks"] if c["severity"] in ("blocker", "warning")]
        if not any(c["severity"] == "blocker" for c in check["checks"]) or rounds >= max_rounds:
            break
        rounds += 1
        issues = [{"claim_id": c["claim_id"], "severity": c["severity"], "message": "; ".join(c["issues"]) + (f" Vorschlag: {c['fix']}" if c.get("fix") else "")} for c in problems]
        draft = ctx.runner.run("section-analyst", {**write_in, "evidence": ev, "previous_claims": draft["claims"], "issues": issues, "round": rounds}, report_id=rid)
        draft = _take_new_evidence(ctx, rid, sec["key"], draft, ev, ev_by_id, passages)

    # persist (replaces an earlier run of the same section and version)
    checks = {c["claim_id"]: c for c in check["checks"]}
    with ctx.db.session() as s:
        for model in (Claim, Calculation):
            for row in s.query(model).filter_by(report_id=rid, section_key=sec["key"], version_no=ver).all():
                s.delete(row)
        for row in s.query(Flag).filter_by(report_id=rid, section_key=sec["key"], version_no=ver, origin="verifier").all():
            s.delete(row)
        old = draft_of(s, rid, sec["key"], ver)
        if old:
            s.delete(old)
        s.flush()
        calc_id: dict[str, str] = {}
        for c in calc_rows:
            row = Calculation(report_id=rid, section_key=sec["key"], ref=c["id"], label=c["label"], formula=c["formula"], inputs=c["inputs"], value=c["value"], unit=c.get("unit"), error=c["error"], version_no=ver)
            s.add(row)
            s.flush()
            calc_id[c["id"]] = row.id
        claim_id: dict[str, str] = {}
        for pos, c in enumerate(draft["claims"]):
            ck = checks.get(c["id"])
            ok = ck is not None and ck["verdict"] in ("supported", "partly_supported")
            row = Claim(report_id=rid, section_key=sec["key"], ref=c["id"], position=pos, text=c["text"], kind=c["kind"], evidence_ids=c["evidence_ids"],
                        calc_ids=[calc_id[i] for i in c["calc_ids"] if i in calc_id], confidence=c["confidence"], status="verified" if ok else "flagged",
                        verdict=ck["verdict"] if ck else None, issues=ck["issues"] if ck else [], version_no=ver)
            s.add(row)
            s.flush()
            claim_id[c["id"]] = row.id
            if ck and ck["severity"] in ("blocker", "warning"):
                s.add(Flag(report_id=rid, section_key=sec["key"], claim_id=row.id, origin="verifier", kind=ck["verdict"], severity=ck["severity"],
                           text=" ".join(ck["issues"]) or ck["verdict"], version_no=ver))
        charts = []
        for ch in draft["charts"]:
            allowed = [float(ev_by_id[i]["value"]) for i in ch["evidence_ids"] if i in ev_by_id and ev_by_id[i]["value"] is not None]
            allowed += [c["value"] for c in calcs if c["id"] in ch["calc_ids"]]
            if all(any(_close(v, a) for a in allowed) for v in ch["values"]):  # a number on a chart must be a number from the ledger
                charts.append({**ch, "calc_ids": [calc_id[i] for i in ch["calc_ids"] if i in calc_id], "claim_ids": [claim_id[i] for i in ch["claim_ids"] if i in claim_id]})
        blockers = any(c["severity"] == "blocker" for c in check["checks"])
        s.add(SectionDraft(report_id=rid, section_key=sec["key"], version_no=ver, headline=draft["headline"], charts=charts, open_points=draft["open_points"], rounds=rounds, verified=not blockers))


def _take_new_evidence(ctx: Context, rid: str, section_key: str, draft: dict, ev: list[dict], ev_by_id: dict, passages: list[dict]) -> dict:
    """Findings the analyst took from the raw text become evidence in the ledger (they were checked against the passage); claims then cite real ids."""
    new = draft.get("new_evidence") or []
    if not new:
        return draft
    from ..models import Source

    by_pid = {p["id"]: p for p in passages}
    remap: dict[str, str] = {}
    with ctx.db.session() as s:
        have = {(e.section_key, e.statement.lower()): e.id for e in s.query(Evidence).filter_by(report_id=rid).all()}
        srcs = {x.id: x for x in s.query(Source).filter(Source.report_id == rid).all()}
        for n in new:
            sig = (section_key, n["statement"].lower())
            if sig in have:
                remap[n["id"]] = have[sig]
                continue
            sid = n["passage_id"].split("#")[0]
            src = srcs.get(sid)
            row = Evidence(report_id=rid, section_key=section_key, origin="web" if src and src.kind == "web" else "document", source_id=sid, kind=n["kind"], statement=n["statement"],
                           quote=n["quote"], locator=by_pid.get(n["passage_id"], {}).get("locator", "")[:300], value=n.get("value"), unit=n.get("unit"), entity=n.get("entity"),
                           period=n.get("period"), confidence=0.75)
            s.add(row)
            s.flush()
            have[sig] = row.id
            remap[n["id"]] = row.id
            ref = {"id": row.id, "kind": row.kind, "statement": row.statement, "quote": row.quote, "value": row.value, "unit": row.unit,
                   "source": f"{src.title}, {row.locator}" if src else row.locator, "user_provided": False}
            if row.id not in ev_by_id:
                ev.append(ref)
                ev_by_id[row.id] = ref
    for c in draft["claims"]:
        c["evidence_ids"] = [remap.get(i, i) for i in c["evidence_ids"]]
    for ch in draft["charts"]:
        ch["evidence_ids"] = [remap.get(i, i) for i in ch["evidence_ids"]]
    return {**draft, "new_evidence": []}


def run_red_team(ctx: Context, rid: str, ver: int, base: dict) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        sections = []
        for o in outline(s, rid):
            d = draft_of(s, rid, o.key, ver)
            claims = [claim_payload(c) for c in current_claims(s, rid, ver, o.key) if c.status != "rejected"]
            sections.append({"key": o.key, "title": o.title, "headline": d.headline if d else "", "claims": claims, "open_points": d.open_points if d else [], "verified": d.verified if d else True})
        decision = r.decision_requested
    out = ctx.runner.run("red-team", {"lang": base["lang"], "topic": base["topic"], "committee": base["committee"], "decision_requested": decision, "sections": sections}, report_id=rid)
    with ctx.db.session() as s:
        for f in s.query(Flag).filter_by(report_id=rid, origin="red_team", version_no=ver).all():
            s.delete(f)
        s.flush()
        for c in out["challenges"]:
            s.add(Flag(report_id=rid, section_key=c.get("section_key"), claim_id=c.get("claim_id"), origin="red_team", kind=c["kind"], severity=c["severity"], text=c["text"], version_no=ver))
        r = get_report(s, rid)
        log_event(s, rid, "red_team", verdict=out.get("verdict"), challenges=len(out["challenges"]))


def reverify_claim(ctx: Context, rid: str, claim_id: str) -> dict:
    """A claim the user edited is checked again against the same evidence before it can be approved."""
    with ctx.db.session() as s:
        c = s.get(Claim, claim_id)
        r = get_report(s, rid)
        base_lang = r.lang
        ev = evidence_refs(s, rid, c.section_key)
        have = {e["id"] for e in ev}
        extra = [x for x in s.query(Evidence).filter(Evidence.id.in_(c.evidence_ids)).all() if x.id not in have]
        for x in extra:
            ev.append({"id": x.id, "kind": x.kind, "statement": x.statement, "quote": x.quote, "value": x.value, "unit": x.unit, "source": x.locator, "user_provided": x.origin == "user"})
        calcs = [calc_payload(k) for k in s.query(Calculation).filter(Calculation.id.in_(c.calc_ids)).all() if k.value is not None]
        payload = {"lang": base_lang, "section_key": c.section_key, "claims": [claim_payload(c)], "evidence": ev, "calculations": calcs}
        sec_key, ver = c.section_key, c.version_no
    out = ctx.runner.run("verifier", payload, report_id=rid)
    ck = out["checks"][0]
    with ctx.db.session() as s:
        c = s.get(Claim, claim_id)
        ok = ck["verdict"] in ("supported", "partly_supported")
        c.verdict, c.issues, c.status = ck["verdict"], ck["issues"], ("verified" if ok else "flagged")
        for f in s.query(Flag).filter_by(report_id=rid, claim_id=claim_id, origin="verifier", status="open").all():
            f.status, f.resolution = "resolved", "fixed" if ok else f.resolution
        if ck["severity"] in ("blocker", "warning"):
            s.add(Flag(report_id=rid, section_key=sec_key, claim_id=claim_id, origin="verifier", kind=ck["verdict"], severity=ck["severity"], text=" ".join(ck["issues"]) or ck["verdict"], version_no=ver))
        return {"verdict": ck["verdict"], "severity": ck["severity"], "issues": ck["issues"]}
