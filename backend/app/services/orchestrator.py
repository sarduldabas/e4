"""The orchestrator: owns the case state, decides what runs next, enforces the three checkpoints.
Plain Python, no agent framework. Agents are called only through `ctx.runner`, never by each other."""
from __future__ import annotations

from datetime import datetime

from ..core.parsers import SUPPORTED, kind_of
from ..core.storage import safe_name, sha256
from ..models import AgentRun, Asset, Calculation, Claim, Deck, Event, Evidence, FileRow, Flag, Job, Report, SectionDraft, Slide, Source
from . import analyse, collect, feedback, generate, outline as outline_svc
from .ctx import (Blocked, Context, NotFound, StateError, calc_payload, claim_payload, current_claims, draft_of, get_report, log_event, open_blockers, outline,
                  require_state, set_state)
from .jobs import Busy, Progress


class Orchestrator:
    def __init__(self, ctx: Context):
        self.ctx = ctx

    # ------------------------------------------------------------------ the case itself
    def case(self, rid: str) -> dict:
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            ver = r.version_no
            job = s.query(Job).filter_by(report_id=rid).order_by(Job.created_at.desc()).first()
            blockers = open_blockers(s, rid, ver)
            deck = s.query(Deck).filter_by(report_id=rid, version_no=ver).first()
            counts = {
                "files": s.query(FileRow).filter_by(report_id=rid).count(),
                "sources": s.query(Source).filter(Source.report_id == rid, Source.status == "parsed").count(),
                "evidence": s.query(Evidence).filter_by(report_id=rid, status="active").count(),
                "claims": s.query(Claim).filter(Claim.report_id == rid, Claim.version_no == ver, Claim.status != "rejected").count(),
                "approved_claims": s.query(Claim).filter_by(report_id=rid, version_no=ver, status="approved").count(),
                "slides": s.query(Slide).filter_by(report_id=rid, version_no=ver).count(),
            }
            return {"id": r.id, "title": r.title, "topic": r.topic, "description": r.description, "decision_requested": r.decision_requested, "lang": r.lang, "links": r.links or [],
                    "committee": r.committee, "date": r.date, "version": r.version, "version_no": ver, "state": r.state, "stage": r.stage, "counts": counts,
                    "open_blockers": len(blockers), "deck": {"version": deck.version_no, "slides": deck.slide_count, "changes": deck.changes} if deck else None,
                    "job": self._job_view(job) if job else None}

    @staticmethod
    def _job_view(j: Job) -> dict:
        return {"id": j.id, "kind": j.kind, "status": j.status, "progress": j.progress, "error": j.error,
                "started_at": j.started_at.isoformat() if j.started_at else None, "finished_at": j.finished_at.isoformat() if j.finished_at else None}

    def job(self, rid: str, job_id: str) -> dict:
        with self.ctx.db.session() as s:
            j = s.get(Job, job_id)
            if not j or j.report_id != rid:
                raise NotFound(job_id)
            return self._job_view(j)

    def set_case(self, rid: str, data: dict) -> dict:
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            if r.state not in ("SETUP", "OUTLINE_REVIEW"):
                raise StateError("the brief can only be changed before the research starts")
            for k in ("topic", "description", "decision_requested", "lang", "title"):
                if data.get(k) is not None:
                    setattr(r, k, data[k])
            if data.get("links") is not None:
                r.links = [str(x)[:500] for x in data["links"]][:50]
            if data.get("committee_id"):
                from ..models import Committee
                c = s.get(Committee, data["committee_id"])
                if c:
                    r.committee_id, r.committee, r.date = c.id, c.name, c.date
            log_event(s, rid, "brief_saved")
        return self.case(rid)

    # ------------------------------------------------------------------ files
    def add_file(self, rid: str, role: str, name: str, data: bytes) -> dict:
        if role not in ("template", "source", "prior_report"):
            raise ValueError("role must be template, source or prior_report")
        kind = kind_of(name)
        if role == "template" and kind not in ("pptx", "potx"):
            raise ValueError("the template must be a .pptx file")
        if kind not in SUPPORTED and role != "template":
            raise ValueError(f"file type .{kind} is not supported (supported: {', '.join(sorted(SUPPORTED))})")
        if len(data) > self.ctx.settings.max_upload_mb * 1024 * 1024:
            raise ValueError(f"file larger than {self.ctx.settings.max_upload_mb} MB")
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            if r.state not in ("SETUP", "OUTLINE_REVIEW", "COLLECTING", "FEEDBACK", "DECK_REVIEW", "FINDINGS_REVIEW", "FINAL"):
                raise StateError("files can not be added now")
            f = FileRow(report_id=rid, role=role, name=safe_name(name), kind=kind, key="", size=len(data), sha256=sha256(data))
            s.add(f)
            s.flush()
            f.key = self.ctx.store.put(f"reports/{rid}/files/{f.id}-{f.name}", data)
            log_event(s, rid, "file_added", name=f.name, role=role)
            return self._file_view(f)

    @staticmethod
    def _file_view(f: FileRow) -> dict:
        return {"id": f.id, "role": f.role, "name": f.name, "kind": f.kind, "size": f.size}

    def files(self, rid: str) -> list[dict]:
        with self.ctx.db.session() as s:
            get_report(s, rid)
            return [self._file_view(f) for f in s.query(FileRow).filter_by(report_id=rid).order_by(FileRow.created_at).all()]

    def delete_file(self, rid: str, fid: str) -> None:
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            require_state(r, "SETUP", "OUTLINE_REVIEW")
            f = s.get(FileRow, fid)
            if not f or f.report_id != rid:
                raise NotFound(fid)
            self.ctx.store.delete_prefix(f.key)
            s.delete(f)

    def sources(self, rid: str) -> list[dict]:
        with self.ctx.db.session() as s:
            get_report(s, rid)
            return [{"id": x.id, "kind": x.kind, "title": x.title, "status": x.status, "relevance": x.relevance, "section_keys": x.section_keys, "reason": x.reason,
                     "chunks": x.chunk_count, "error": x.error, "duplicate_of": x.duplicate_of} for x in s.query(Source).filter_by(report_id=rid).order_by(Source.created_at).all()]

    # ------------------------------------------------------------------ checkpoint 1: outline
    def propose_outline(self, rid: str) -> dict:
        return outline_svc.propose_outline(self.ctx, rid)

    def get_outline(self, rid: str) -> list[dict]:
        return outline_svc.get_outline(self.ctx, rid)

    def update_outline(self, rid: str, sections: list[dict]) -> list[dict]:
        return outline_svc.update_outline(self.ctx, rid, sections)

    def interview(self, rid: str, text: str = "", done: bool = False) -> dict:
        return outline_svc.interview_turn(self.ctx, rid, text, done)

    def get_interview(self, rid: str) -> dict:
        return outline_svc.get_interview(self.ctx, rid)

    def approve_outline(self, rid: str) -> str:
        """Checkpoint 1. Starts collecting and analysing; the job ends at checkpoint 2."""
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            if r.state not in ("OUTLINE_REVIEW", "COLLECTING", "ANALYSING", "FINDINGS_REVIEW"):
                raise StateError(f"the outline can not be approved in state {r.state}")
            if not outline(s, rid):
                raise Blocked("the outline has no sections")
            if r.state == "FINDINGS_REVIEW":
                raise StateError("research already done; use re-run")
            log_event(s, rid, "outline_approved", sections=len(outline(s, rid)))

        def job(prog: Progress) -> None:
            collect.run_collect(self.ctx, rid, prog)
            analyse.run_analyse(self.ctx, rid, prog)

        return self.ctx.jobs.submit(rid, "research", job)

    def rerun_research(self, rid: str, sections: list[str] | None = None) -> str:
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            require_state(r, "FINDINGS_REVIEW", "COLLECTING", "ANALYSING")
            log_event(s, rid, "rerun", sections=sections or "all")

        def job(prog: Progress) -> None:
            collect.run_collect(self.ctx, rid, prog, only=sections)
            analyse.run_analyse(self.ctx, rid, prog, only=sections)

        return self.ctx.jobs.submit(rid, "research", job)

    # ------------------------------------------------------------------ checkpoint 2: findings
    def findings(self, rid: str) -> dict:
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            ver = r.version_no
            ev = {e.id: e for e in s.query(Evidence).filter_by(report_id=rid).all()}
            srcs = {x.id: x for x in s.query(Source).filter_by(report_id=rid).all()}
            calcs = {c.id: c for c in s.query(Calculation).filter_by(report_id=rid, version_no=ver).all()}
            flags = s.query(Flag).filter_by(report_id=rid, version_no=ver).order_by(Flag.created_at).all()
            sections = []
            for o in outline(s, rid):
                d = draft_of(s, rid, o.key, ver)
                claims = []
                for c in current_claims(s, rid, ver, o.key):
                    claims.append({
                        "id": c.id, "text": c.text, "kind": c.kind, "status": c.status, "verdict": c.verdict, "issues": c.issues, "confidence": c.confidence, "user_edited": c.user_edited,
                        "evidence": [{"id": e.id, "statement": e.statement, "quote": e.quote, "locator": e.locator, "origin": e.origin, "value": e.value, "unit": e.unit,
                                      "source": ("Ihre Angabe" if e.origin == "user" else srcs[e.source_id].title if e.source_id in srcs else "")} for e in (ev.get(i) for i in c.evidence_ids) if e],
                        "calculations": [{"id": k.id, "label": k.label, "formula": k.formula, "value": k.value, "unit": k.unit} for k in (calcs.get(i) for i in c.calc_ids) if k]})
                sections.append({"key": o.key, "title": o.title, "headline": d.headline if d else "", "verified": d.verified if d else None, "open_points": d.open_points if d else [],
                                 "charts": d.charts if d else [], "claims": claims,
                                 "flags": [self._flag_view(f) for f in flags if f.section_key == o.key]})
            return {"version": r.version, "state": r.state, "sections": sections, "general_flags": [self._flag_view(f) for f in flags if not f.section_key],
                    "open_blockers": sum(1 for f in flags if f.status == "open" and f.severity == "blocker")}

    @staticmethod
    def _flag_view(f: Flag) -> dict:
        return {"id": f.id, "claim_id": f.claim_id, "section_key": f.section_key, "origin": f.origin, "kind": f.kind, "severity": f.severity, "text": f.text,
                "status": f.status, "resolution": f.resolution, "note": f.note}

    def update_claim(self, rid: str, claim_id: str, text: str | None = None, status: str | None = None) -> dict:
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            require_state(r, "FINDINGS_REVIEW")
            c = s.get(Claim, claim_id)
            if not c or c.report_id != rid or c.version_no != r.version_no:
                raise NotFound(claim_id)
            if text is not None and text.strip() and text.strip() != c.text:
                c.text, c.user_edited, c.status = text.strip(), True, "draft"
                log_event(s, rid, "claim_edited", claim=claim_id)
                edited = True
            else:
                edited = False
            if status:
                if status not in ("approved", "rejected", "verified"):
                    raise ValueError("status must be approved, rejected or verified")
                if status == "approved" and c.status == "flagged" and not edited:
                    raise Blocked("resolve the verifier flag on this claim first")
                if status == "rejected":
                    c.status = "rejected"
                    for f in s.query(Flag).filter_by(report_id=rid, claim_id=claim_id, status="open").all():
                        f.status, f.resolution = "resolved", "rejected"
                    log_event(s, rid, "claim_rejected", claim=claim_id)
                elif not edited:
                    c.status = status
        result = analyse.reverify_claim(self.ctx, rid, claim_id) if edited else None  # an edited claim is verified again before it counts
        with self.ctx.db.session() as s:
            c = s.get(Claim, claim_id)
            if edited and status == "approved" and c.status == "verified":
                c.status = "approved"
            return {"id": c.id, "text": c.text, "status": c.status, "verdict": c.verdict, "issues": c.issues, "reverified": result}

    def resolve_flag(self, rid: str, flag_id: str, resolution: str, note: str | None = None) -> dict:
        if resolution not in ("accepted", "dismissed", "rejected"):
            raise ValueError("resolution must be accepted, dismissed or rejected")
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            require_state(r, "FINDINGS_REVIEW")
            f = s.get(Flag, flag_id)
            if not f or f.report_id != rid:
                raise NotFound(flag_id)
            if f.severity == "blocker" and resolution in ("accepted", "dismissed") and not (note and note.strip()):
                raise Blocked("a blocker can only be accepted with a short reason (it is kept in the record)")
            if resolution == "rejected":
                if not f.claim_id:
                    raise ValueError("only a flag on a claim can be resolved by rejecting the claim")
                c = s.get(Claim, f.claim_id)
                c.status = "rejected"
            elif f.origin == "verifier" and f.claim_id and resolution == "accepted":
                c = s.get(Claim, f.claim_id)
                if c and c.status == "flagged":
                    c.status = "verified"
            f.status, f.resolution, f.note = "resolved", resolution, note
            log_event(s, rid, "flag_resolved", flag=flag_id, resolution=resolution, severity=f.severity, note=note)
            return self._flag_view(f)

    def approve_findings(self, rid: str) -> str:
        """Checkpoint 2. Blocked while any blocker flag is open. Starts slide generation."""
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            require_state(r, "FINDINGS_REVIEW")
            blockers = open_blockers(s, rid, r.version_no)
            if blockers:
                raise Blocked(f"{len(blockers)} blocker(s) must be resolved first", [self._flag_view(f) for f in blockers])
            n = 0
            for c in current_claims(s, rid, r.version_no, None, ("verified", "approved")):
                if c.status != "approved":
                    c.status, n = "approved", n + 1
            if not s.query(Claim).filter_by(report_id=rid, version_no=r.version_no, status="approved").count():
                raise Blocked("there is no approved claim: the deck would be empty")
            log_event(s, rid, "findings_approved", claims=n, version=r.version_no)
        instr = feedback.pending_instructions(self.ctx, rid)
        return self.ctx.jobs.submit(rid, "generate", lambda prog: generate.run_generate(self.ctx, rid, prog, instructions=instr or None))

    # ------------------------------------------------------------------ checkpoint 3: deck
    def deck(self, rid: str) -> dict:
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            ver = r.version_no
            order = {o.key: o.position for o in outline(s, rid)}
            titles = {o.key: o.title for o in outline(s, rid)}
            slides = [x for x in s.query(Slide).filter_by(report_id=rid, version_no=ver).all() if x.section_key in order]
            slides.sort(key=lambda x: (order[x.section_key], x.position))
            claims = {c.id: c for c in s.query(Claim).filter_by(report_id=rid, version_no=ver).all()}
            d = s.query(Deck).filter_by(report_id=rid, version_no=ver).first()
            return {"version": r.version, "state": r.state, "has_file": bool(d), "changes": d.changes if d else [],
                    "slides": [{"id": x.id, "section_key": x.section_key, "section": titles[x.section_key], "title": x.title, "bullets": x.bullets, "chart": x.chart, "notes": x.notes,
                                "asset_ids": x.asset_ids, "user_edited": x.user_edited,
                                "claims": [{"id": cid, "text": claims[cid].text} for cid in dict.fromkeys(c for b in x.bullets for c in b.get("claim_ids", [])) if cid in claims]} for x in slides]}

    def update_slide(self, rid: str, slide_id: str, title: str | None = None, bullets: list[str] | None = None) -> dict:
        warnings: list[str] = []
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            require_state(r, "DECK_REVIEW")
            sl = s.get(Slide, slide_id)
            if not sl or sl.report_id != rid or sl.version_no != r.version_no:
                raise NotFound(slide_id)
            if title is not None and title.strip():
                sl.title = title.strip()[:300]
            if bullets is not None:
                from .ctx import numbers_in
                old = sl.bullets
                claims = {c.id: c.text for c in s.query(Claim).filter_by(report_id=rid, version_no=r.version_no).all()}
                known = set().union(*[numbers_in(claims.get(cid, "")) for b in old for cid in b.get("claim_ids", [])]) if old else set()
                new = []
                for i, t in enumerate(b.strip() for b in bullets if b.strip()):
                    ids = old[i]["claim_ids"] if i < len(old) else []
                    extra = numbers_in(t) - known - numbers_in(sl.title)
                    if extra:
                        warnings.append(f"„{t[:40]}…“: {', '.join(sorted(extra))} " + ("steht in keiner belegten Aussage." if r.lang == "de" else "is not in any verified claim."))
                    new.append({"text": t, "claim_ids": ids})
                sl.bullets = new
            sl.user_edited = True
            log_event(s, rid, "slide_edited", slide=slide_id, warnings=len(warnings))
        generate.build_deck_file(self.ctx, rid)
        return {"id": slide_id, "warnings": warnings}

    def reorder_slides(self, rid: str, section_order: list[str]) -> list[str]:
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            require_state(r, "DECK_REVIEW")
            rows = {o.key: o for o in outline(s, rid)}
            if set(section_order) != set(rows):
                raise ValueError("send every section key exactly once")
            for i, k in enumerate(section_order):
                rows[k].position = i
            log_event(s, rid, "reordered", order=section_order)
        generate.build_deck_file(self.ctx, rid)
        return section_order

    def deck_file(self, rid: str) -> tuple[str, bytes]:
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            d = s.query(Deck).filter_by(report_id=rid, version_no=r.version_no).first()
            if not d:
                raise NotFound("no deck yet")
            name = f"{safe_name(r.title)[:60]}_{r.version}.pptx"
            key = d.key
        return name, self.ctx.store.get(key)

    def finalize(self, rid: str) -> dict:
        """Checkpoint 3."""
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            require_state(r, "DECK_REVIEW")
            if not s.query(Deck).filter_by(report_id=rid, version_no=r.version_no).first():
                raise Blocked("there is no deck to finalise")
            set_state(s, r, "FINAL")
            r.status = "Presented"
            log_event(s, rid, "deck_final", version=r.version)
        return self.case(rid)

    # ------------------------------------------------------------------ feedback and the next version
    def submit_feedback(self, rid: str, text: str, selected_slide_id: str | None = None) -> dict:
        return feedback.interpret(self.ctx, rid, text, selected_slide_id)

    def apply_feedback(self, rid: str, feedback_id: str) -> str:
        return self.ctx.jobs.submit(rid, "feedback", lambda prog: feedback.run_feedback(self.ctx, rid, prog, feedback_id))

    # ------------------------------------------------------------------ audit
    def events(self, rid: str) -> list[dict]:
        with self.ctx.db.session() as s:
            get_report(s, rid)
            return [{"kind": e.kind, "payload": e.payload, "at": e.created_at.isoformat()} for e in s.query(Event).filter_by(report_id=rid).order_by(Event.created_at, Event.id).all()]

    def agent_runs(self, rid: str, with_io: bool = False) -> list[dict]:
        with self.ctx.db.session() as s:
            get_report(s, rid)
            rows = s.query(AgentRun).filter_by(report_id=rid).order_by(AgentRun.created_at, AgentRun.id).all()
            return [{"id": a.id, "agent": a.agent_id, "mode": a.mode, "model": a.model, "status": a.status, "error": a.error, "note": a.note, "duration_ms": a.duration_ms, "usage": a.usage,
                     "at": a.created_at.isoformat(), **({"input": a.input, "output": a.output} if with_io else {})} for a in rows]

    def purge(self, rid: str) -> None:
        """Called when a report is deleted: its files and its audit trail go with it."""
        self.ctx.store.delete_prefix(f"reports/{rid}")
        with self.ctx.db.session() as s:
            s.query(AgentRun).filter_by(report_id=rid).delete()
