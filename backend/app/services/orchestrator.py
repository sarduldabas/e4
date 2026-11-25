"""The orchestrator: owns the case state, decides what runs next, enforces the three checkpoints.
Plain Python, no agent framework. Agents are called only through `ctx.runner`, never by each other."""
from __future__ import annotations

from datetime import datetime

from ..core.parsers import SUPPORTED, kind_of
from ..core.storage import safe_name, sha256
from ..models import AgentRun, Asset, Calculation, Claim, Deck, Event, Evidence, FileRow, Flag, Job, Report, SectionDraft, Slide, Source
from . import slides as slides_service
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
                    "use_web": bool(r.use_web), "web_enabled": self.ctx.settings.allow_web, "committee": r.committee, "date": r.date, "version": r.version, "version_no": ver, "state": r.state, "stage": r.stage, "counts": counts,
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
            if data.get("use_web") is not None:
                r.use_web = bool(data["use_web"])
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
            from .ingest import preflight
            f = FileRow(report_id=rid, role=role, name=safe_name(name), kind=kind, key="", size=len(data), sha256=sha256(data),
                        info=preflight(name, data) if role != "template" else None)
            s.add(f)
            s.flush()
            f.key = self.ctx.store.put(f"reports/{rid}/files/{f.id}-{f.name}", data)
            log_event(s, rid, "file_added", name=f.name, role=role)
            return self._file_view(f)

    @staticmethod
    def _file_view(f: FileRow) -> dict:
        return {"id": f.id, "role": f.role, "name": f.name, "kind": f.kind, "size": f.size, "info": f.info}

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
                     "chunks": x.chunk_count, "error": x.error, "duplicate_of": x.duplicate_of, "ref": x.ref if x.kind == "web" and x.ref.startswith("http") else None,
                     "info": x.info} for x in s.query(Source).filter_by(report_id=rid).order_by(Source.created_at).all()]

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
        return slides_service.deck_view(self.ctx, rid)

    def update_slide(self, rid: str, slide_id: str, title: str | None = None, bullets: list[str] | None = None, spec: dict | None = None) -> dict:
        return slides_service.patch_slide(self.ctx, rid, slide_id, title=title, bullets=bullets, spec=spec)

    def revise_slide(self, rid: str, slide_id: str, instruction: str) -> dict:
        return slides_service.revise_slide(self.ctx, rid, slide_id, instruction)

    def undo_slide(self, rid: str, slide_id: str) -> dict:
        return slides_service.undo_slide(self.ctx, rid, slide_id)

    def add_slide(self, rid: str, after: str | None, layout: str) -> dict:
        return slides_service.add_slide(self.ctx, rid, after, layout)

    def delete_slide(self, rid: str, slide_id: str) -> None:
        slides_service.delete_slide(self.ctx, rid, slide_id)

    def move_slide(self, rid: str, slide_id: str, index: int) -> None:
        slides_service.move_slide(self.ctx, rid, slide_id, index)

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
        """The PowerPoint file is built from the slides as they are now, so the download always equals what the page shows."""
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            d = s.query(Deck).filter_by(report_id=rid, version_no=r.version_no).first()
            if not d:
                raise NotFound("no deck yet")
            name = f"{safe_name(r.title)[:60]}_{r.version}.pptx"
        generate.build_deck_file(self.ctx, rid)
        with self.ctx.db.session() as s:
            r = get_report(s, rid)
            key = s.query(Deck).filter_by(report_id=rid, version_no=r.version_no).first().key
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

    def asset_bytes(self, rid: str, asset_id: str) -> tuple[bytes, str]:
        with self.ctx.db.session() as s:
            get_report(s, rid)
            a = s.get(Asset, asset_id)
            if not a or a.report_id != rid or not a.key:
                raise NotFound(asset_id)
            data = self.ctx.store.get(a.key)
        mime = "image/png" if data[:4] == b"\x89PNG" else "image/jpeg" if data[:3] == b"\xff\xd8\xff" else "image/gif" if data[:3] == b"GIF" else "application/octet-stream"
        return data, mime

    def agent_runs(self, rid: str, with_io: bool = False) -> list[dict]:
        with self.ctx.db.session() as s:
            get_report(s, rid)
            rows = s.query(AgentRun).filter_by(report_id=rid).order_by(AgentRun.created_at, AgentRun.id).all()
            return [{"id": a.id, "agent": a.agent_id, "mode": a.mode, "model": a.model, "status": a.status, "error": a.error, "note": a.note, "duration_ms": a.duration_ms, "usage": a.usage,
                     "at": a.created_at.isoformat(), **({"input": a.input, "output": a.output} if with_io else {})} for a in rows]

    def agent_summary(self, rid: str) -> dict:
        """The audit view: calls, tokens and time per agent, and which calls ran on the model and which on the rules version."""
        with self.ctx.db.session() as s:
            get_report(s, rid)
            rows = s.query(AgentRun).filter_by(report_id=rid).order_by(AgentRun.created_at, AgentRun.id).all()
            per: dict[str, dict] = {}
            for a in rows:
                p = per.setdefault(a.agent_id, {"agent": a.agent_id, "calls": 0, "llm": 0, "rules": 0, "errors": 0, "prompt_tokens": 0, "completion_tokens": 0, "duration_ms": 0, "models": set()})
                p["calls"] += 1
                if a.status != "ok":
                    p["errors"] += 1
                elif a.mode == "llm":
                    p["llm"] += 1
                else:
                    p["rules"] += 1
                p["prompt_tokens"] += int((a.usage or {}).get("prompt_tokens", 0) or 0)
                p["completion_tokens"] += int((a.usage or {}).get("completion_tokens", 0) or 0)
                p["duration_ms"] += a.duration_ms or 0
                if a.model:
                    p["models"].add(a.model)
            agents = sorted(({**p, "models": sorted(p["models"])} for p in per.values()), key=lambda p: -p["duration_ms"])
            tot = {"calls": len(rows), "llm": sum(p["llm"] for p in agents), "rules": sum(p["rules"] for p in agents), "errors": sum(p["errors"] for p in agents),
                   "prompt_tokens": sum(p["prompt_tokens"] for p in agents), "completion_tokens": sum(p["completion_tokens"] for p in agents), "duration_ms": sum(p["duration_ms"] for p in agents)}
            return {"total": tot, "agents": agents}

    def purge(self, rid: str) -> None:
        """Called when a report is deleted: its files and its audit trail go with it."""
        self.ctx.store.delete_prefix(f"reports/{rid}")
        with self.ctx.db.session() as s:
            s.query(AgentRun).filter_by(report_id=rid).delete()
