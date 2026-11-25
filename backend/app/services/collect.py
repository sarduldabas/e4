"""Stage 2, first half: research. Order of work:
  1. the author's own material is read completely and its evidence extracted (code reads, the vision model reads what code cannot)
  2. the research planner looks at what that material covers and plans, for THIS topic, where to look for the rest: web, SharePoint, mail, Jira, Confluence ...
  3. the plan is carried out: connectors are searched, the web is searched (Foundry web search tool) and the cited pages are read in full
  4. gap rounds: what is still thin per section is planned and searched again
  5. the asset library: pictures are looked at, cropped, charts are read and become evidence, the curator chooses what goes on which slide
Nothing that fits in the budget is left unread."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from ..core.connectors import CATALOG, KINDS
from ..core.ingest.model import Image
from ..models import Evidence, FileRow, Source
from .ctx import Context, get_report, log_event, outline, set_state
from . import assets as assets_svc
from .ingest import read_document
from .jobs import Progress
from .retrieval import select_for_extraction

MAX_WEB_PAGES = 10  # cited pages that are fetched and read in full, over all searches
CAP_BY_KIND = {"search": 0.6, "page": 0.7}  # confidence ceiling of evidence from a search briefing / a fetched page


def _read_source(ctx: Context, src: Source) -> tuple[str, bytes]:
    if src.kind == "web":
        return ctx.web.fetch_document(src.ref)
    if src.file_id:
        with ctx.db.session() as s:
            f = s.get(FileRow, src.file_id)
        return f.name, ctx.store.get(f.key)
    return ctx.connectors[src.kind].fetch(src.ref)


def _batches(chunks: list[dict], limit: int) -> list[list[dict]]:
    """Chunks in reading order, grouped so that one call sees about `limit` characters (a table is never cut in the middle: chunks are whole)."""
    out, cur, size = [], [], 0
    for c in chunks:
        if cur and size + len(c["text"]) > limit:
            out.append(cur)
            cur, size = [], 0
        cur.append(c)
        size += len(c["text"])
    if cur:
        out.append(cur)
    return out


def _web_pictures(ctx: Context, html: bytes, url: str) -> list[Image]:
    """A page's own pictures (never decoration; the rights stay with the publisher). A page whose pictures cannot be fetched is still read."""
    out: list[Image] = []
    try:
        from ..core.ingest.media import dims

        for pic in ctx.web.page_images(html, url, limit=4):
            w, h = dims(pic["data"])
            if w and h and w >= 400 and h >= 220:
                out.append(Image(pic["data"], pic["ext"], w, h, pic["caption"], f"Web {pic['host']}", origin="web", rights=f"Web: {pic['url']}"[:200], context=pic["caption"]))
    except Exception:  # noqa: BLE001
        return []
    return out


def _tok(text: str) -> set[str]:
    from .retrieval import tokens
    return set(tokens(text or ""))


class _Round:
    """One run of the collection. Keeps what has been read, so every later step (and every gap round) only does what is new."""

    def __init__(self, ctx: Context, rid: str, prog: Progress, base: dict, sections: list[dict], lang: str):
        self.ctx, self.rid, self.prog, self.base, self.sections, self.lang = ctx, rid, prog, base, sections, lang
        self.origin_of: dict[str, str] = {}
        self.cap_of: dict[str, float] = {}
        self.parsed: list[str] = []
        self.extracted: set[str] = set()
        self.skipped_total = 0
        self.known_refs: set[str] = set()
        self.added = 0
        self.web_note: str | None = None
        self.web_mode: str | None = None

    # ------------------------------------------------------------------ small helpers
    def store_doc(self, sid: str, doc: dict, info: dict | None) -> None:
        key = f"reports/{self.rid}/parsed/{sid}.json"
        self.ctx.store.put(key, json.dumps(doc, ensure_ascii=False).encode("utf-8"))
        with self.ctx.db.session() as s:
            src = s.get(Source, sid)
            src.status, src.parsed_key, src.chunk_count, src.error, src.info = "parsed", key, len(doc["chunks"]), None, info

    def coverage(self) -> list[dict]:
        with self.ctx.db.session() as s:
            rows = s.query(Evidence).filter_by(report_id=self.rid, status="active").all()
        out = []
        for sec in self.sections:
            mine = [e for e in rows if e.section_key == sec["key"]]
            missing = [ri for ri in sec.get("required_inputs", []) if not any(len(_tok(ri) & _tok(e.statement)) >= max(1, len(_tok(ri)) // 2) for e in mine)]
            top = sorted(mine, key=lambda e: -e.confidence)[:3]
            out.append({"section_key": sec["key"], "evidence": len(mine), "numbers": sum(1 for e in mine if e.value is not None), "internal": sum(1 for e in mine if e.origin != "web"),
                        "external": sum(1 for e in mine if e.origin == "web"), "missing": missing[:4], "examples": [e.statement[:160] for e in top]})
        return out

    def inventory(self) -> list[dict]:
        out = []
        with self.ctx.db.session() as s:
            for src in s.query(Source).filter_by(report_id=self.rid, status="parsed").all():
                summary = ""
                try:
                    data = json.loads(self.ctx.store.get(src.parsed_key))
                    summary = " ".join(c["text"] for c in data["chunks"][:2])[:320]
                except Exception:  # noqa: BLE001
                    pass
                out.append({"id": src.id, "name": src.title[:120], "kind": src.kind, "summary": summary, "status": (src.info or {}).get("status", "")})
        return out[:40]

    def catalogue(self, kinds: list[str], web_ok: bool) -> list[dict]:
        return [{"kind": k, **CATALOG.get(k, {"label": k, "description": "", "query_style": ""})} for k in kinds + (["web"] if web_ok else [])]

    # ------------------------------------------------------------------ own material and links
    def add_own(self, uploads: list[FileRow], links: list[str]) -> None:
        with self.ctx.db.session() as s:
            for f in uploads:
                ref = f"upload:{f.id}"
                if ref not in self.known_refs:
                    s.add(Source(report_id=self.rid, kind="files", title=f.name.rsplit(".", 1)[0], ref=ref, file_id=f.id, status="candidate"))
                    self.known_refs.add(ref)
            for url in links:
                if self.ctx.settings.allow_web and url not in self.known_refs:
                    s.add(Source(report_id=self.rid, kind="web", title=url[:120], ref=url, status="candidate"))
                    self.known_refs.add(url)

    # ------------------------------------------------------------------ screen, read, extract
    def process(self) -> int:
        """Everything that is a candidate or selected but not yet read: screen it, read it completely, extract evidence. Returns the evidence added."""
        ctx, rid = self.ctx, self.rid
        cands = []
        with ctx.db.session() as s:
            for src in s.query(Source).filter_by(report_id=rid, status="candidate").all():
                cands.append({"id": src.id, "title": src.title, "kind": src.kind, "path": src.ref if not src.ref.startswith("upload:") else None, "modified": src.modified,
                              "excerpt": self._excerpt.get(src.id, "") if hasattr(self, "_excerpt") else ""})
        decisions: dict[str, dict] = {}
        if cands:
            self.prog.update("screening", None, None, f"{len(cands)} Kandidaten bewerten")
            out = ctx.runner.run("source-screener", {**self.base, "sections": self.sections, "candidates": cands}, report_id=rid)
            decisions = {d["candidate_id"]: d for d in out["decisions"]}
        with ctx.db.session() as s:
            for src in s.query(Source).filter_by(report_id=rid, status="candidate").all():
                d = decisions.get(src.id)
                mine = bool(src.file_id) or src.kind == "web"  # what the user attached or named is always read
                if d:
                    src.relevance, src.section_keys, src.reason, src.duplicate_of = d["relevance"], d["section_keys"], d["reason"], d["duplicate_of"]
                src.status = "selected" if (mine or (d and d["include"])) else "rejected"
                if mine and d and not d["include"]:
                    src.reason = "vom Nutzer angegeben" if self.lang == "de" else "provided by the user"
        with ctx.db.session() as s:
            todo = [(x.id, x.kind, x.title, x.ref) for x in s.query(Source).filter_by(report_id=rid, status="selected").all()]
        self.prog.update("reading", None, None, f"{len(todo)} Quellen lesen")
        new_ids: list[str] = []
        for sid, kind, title, ref in todo:
            try:
                with ctx.db.session() as s:
                    src = s.get(Source, sid)
                name, data = _read_source(ctx, src)
                p, info = read_document(ctx, rid, name, data, self.lang)
                if kind == "web" and name.lower().endswith((".html", ".htm")) and ctx.settings.allow_web:
                    p.images += _web_pictures(ctx, data, ref)
                doc = {"title": p.title, "kind": p.kind, "chunks": [{"locator": c.locator, "text": c.text} for c in p.chunks]}
                self.store_doc(sid, doc, info)
                with ctx.db.session() as s:
                    src = s.get(Source, sid)
                    if kind == "web" and p.title:
                        src.title = p.title[:200]
                    if src.file_id:
                        f = s.get(FileRow, src.file_id)
                        if f:
                            f.info = info
                    assets_svc.store_parsed(ctx, s, rid, sid, src.title, p)
                new_ids.append(sid)
                self.origin_of[sid] = "web" if kind == "web" else "document"
                self.cap_of[sid] = CAP_BY_KIND["page"] if kind == "web" else 1.0
            except Exception as e:  # noqa: BLE001  one unreadable file must not stop the run
                with ctx.db.session() as s:
                    src = s.get(Source, sid)
                    src.status, src.error = "failed", f"{e.__class__.__name__}: {e}"[:280]
                    src.info = {"status": "failed", "warnings": [str(e)[:200]]}
                    log_event(s, rid, "source_failed", source=src.title, error=str(e)[:200])
        self.parsed += new_ids
        return self.extract(new_ids)

    def extract(self, ids: list[str]) -> int:
        ctx, rid = self.ctx, self.rid
        jobs: list[tuple[str, str, list[dict]]] = []
        for sid in ids:
            if sid in self.extracted:
                continue
            self.extracted.add(sid)
            with ctx.db.session() as s:
                src = s.get(Source, sid)
                title, key = src.title, src.parsed_key
            data = json.loads(ctx.store.get(key))
            chunks, skipped = select_for_extraction(data["chunks"], self.sections, self.base["topic"], ctx.settings.max_extract_chars)
            if skipped:
                self.skipped_total += skipped
                with ctx.db.session() as s:
                    src = s.get(Source, sid)
                    info = dict(src.info or {})
                    info["warnings"] = list(info.get("warnings", [])) + [f"{skipped} von {len(data['chunks'])} Abschnitten nicht ausgewertet (Umfang); die relevantesten zuerst gelesen"]
                    info["status"] = "partial" if info.get("status") == "ok" else info.get("status")
                    src.info = info
            for b in _batches(chunks, ctx.settings.extract_batch_chars):
                jobs.append((sid, title, b))
        self.prog.update("extracting", None, None, f"{len(jobs)} Textabschnitte auswerten")

        def run(job):
            sid, title, chunks = job
            try:
                return sid, ctx.runner.run("evidence-extractor", {**self.base, "sections": self.sections, "document_id": sid, "document_name": title, "chunks": chunks, "max_items": 80}, report_id=rid), None
            except Exception as e:  # noqa: BLE001  the other batches continue
                return sid, None, f"{e.__class__.__name__}: {e}"[:200]

        with ThreadPoolExecutor(max_workers=max(1, ctx.settings.parallel_calls)) as pool:
            results = list(pool.map(run, jobs))
        added = 0
        with ctx.db.session() as s:
            have = {(e.section_key, e.statement.lower()) for e in s.query(Evidence).filter_by(report_id=rid).all()}
            for sid, out, err in results:
                if err:
                    src = s.get(Source, sid)
                    info = dict(src.info or {})
                    info["warnings"] = list(info.get("warnings", [])) + [f"Auswertung eines Abschnitts fehlgeschlagen: {err}"]
                    info["status"] = "partial"
                    src.info = info
                    continue
                for it in out["items"]:
                    sig = (it["section_key"], it["statement"].lower())
                    if sig in have:
                        continue
                    have.add(sig)
                    added += 1
                    s.add(Evidence(report_id=rid, section_key=it["section_key"], origin=self.origin_of.get(sid, "document"), source_id=sid, kind=it["kind"], statement=it["statement"], quote=it["quote"],
                                   locator=it["locator"][:300], value=it.get("value"), unit=it.get("unit"), entity=it.get("entity"), period=it.get("period"),
                                   confidence=min(it.get("confidence", 0.7), self.cap_of.get(sid, 1.0))))
        self.added += added
        return added

    # ------------------------------------------------------------------ carry out a plan
    def execute(self, plan: dict) -> dict:
        """Search connectors and the web with the planned queries. New sources become candidates; web briefings are stored as documents."""
        ctx, rid = self.ctx, self.rid
        stats = {"connector_hits": 0, "web_queries": 0, "web_pages": 0, "web_briefings": 0}
        self._excerpt = {}
        with ctx.db.session() as s:
            for q in plan["queries"]:
                conn = ctx.connectors.get(q["kind"])
                if not conn or q["kind"] == "web":
                    continue
                for h in conn.search(q["query"]):
                    if h.ref in self.known_refs:
                        continue
                    src = Source(report_id=rid, kind=h.kind, title=h.title, ref=h.ref, modified=h.modified, status="candidate")
                    s.add(src)
                    s.flush()
                    self.known_refs.add(h.ref)
                    self._excerpt[src.id] = h.excerpt
                    stats["connector_hits"] += 1
        web_queries = [q for q in plan["queries"] if q["kind"] == "web"][:10]
        if web_queries:
            self.prog.update("searching", None, None, f"{len(web_queries)} Websuchen")
            stats["web_queries"] = len(web_queries)
            try:
                docs, cited, note, mode = _web_search(ctx, rid, self.base, self.sections, web_queries, self.known_refs)
            except Exception as e:  # noqa: BLE001  a failed search must not stop the report
                docs, cited, note, mode = [], [], f"Websuche fehlgeschlagen: {e}"[:300], None
            self.web_note, self.web_mode = note or self.web_note, mode
            for sid, doc in docs:
                self.store_doc(sid, doc, {"status": "ok", "chars": sum(len(c["text"]) for c in doc["chunks"]), "chunks": len(doc["chunks"]), "warnings": [], "origin": "web-search"})
                self.parsed.append(sid)
                self.origin_of[sid], self.cap_of[sid] = "web", CAP_BY_KIND["search"]
            stats["web_briefings"] = len(docs)
            if cited and ctx.settings.allow_web:
                with ctx.db.session() as s:
                    have_pages = s.query(Source).filter(Source.report_id == rid, Source.kind == "web", Source.ref.like("http%")).count()
                    for url in cited:
                        if url not in self.known_refs and have_pages < MAX_WEB_PAGES:
                            s.add(Source(report_id=rid, kind="web", title=url[:200], ref=url, status="selected", reason="von der Websuche zitiert"))
                            self.known_refs.add(url)
                            have_pages += 1
                            stats["web_pages"] += 1
            if note:
                with ctx.db.session() as s:
                    log_event(s, rid, "web_search_note", note=note, mode=mode)
            self.extract([sid for sid, _ in docs])
        return stats


def _web_search(ctx: Context, rid: str, base: dict, sections: list[dict], queries: list[dict], existing: set[str]) -> tuple[list[tuple[str, dict]], list[str], str | None, str | None]:
    """Searches the public web (Foundry web search tool). Returns (briefings as (source id, document), cited urls, note, agent mode)."""
    if not queries:
        return [], [], None, None
    env = ctx.runner.run_env("web-search", {**base, "sections": sections, "queries": [{"id": q["id"], "query": q["query"], "section_keys": q["section_keys"], "why": q.get("why", "")} for q in queries]}, report_id=rid)
    out = env["output"]
    note = out.get("notes") or (None if env.get("mode") == "llm" else env.get("note"))
    docs, urls = [], []
    with ctx.db.session() as s:
        for res in out["results"]:
            ref = "search:" + hashlib.sha1((res["query_id"] + res["briefing"][:200]).encode()).hexdigest()[:12]
            if ref in existing:
                continue
            q = next(x for x in queries if x["id"] == res["query_id"])
            src = Source(report_id=rid, kind="web", title=("Websuche: " + q["query"])[:290], ref=ref, status="selected", relevance=0.6, section_keys=res["section_keys"], reason="Websuche (Foundry)")
            s.add(src)
            s.flush()
            existing.add(ref)
            body = res["briefing"].strip()
            cites = "\n".join(f"- {x['title'] or x['url']} — {x['url']}" for x in res["sources"])
            doc = {"title": src.title, "kind": "search", "chunks": [{"locator": f"Websuche „{q['query']}“", "text": body + (f"\n\nQuellen:\n{cites}" if cites else "")}]}
            docs.append((src.id, doc))
            urls += [x["url"] for x in res["sources"]]
    return docs, urls, note, env.get("mode")


def _plan(ctx: Context, rid: str, rnd: _Round, r_info: dict, kinds: list[str], web_ok: bool, mode: str, number: int, previous: list[str]) -> dict:
    payload = {**rnd.base, "description": r_info["description"], "decision_requested": r_info["decision"], "sections": rnd.sections, "user_statements": r_info["statements"][:20],
               "available_kinds": kinds, "sources": rnd.catalogue(kinds, web_ok), "allow_web": web_ok, "mode": mode, "round": number, "inventory": rnd.inventory(),
               "coverage": rnd.coverage(), "previous_queries": previous[:80], "max_queries": 24 if mode == "initial" else 12}
    return ctx.runner.run("source-planner", payload, report_id=rid)


def run_collect(ctx: Context, rid: str, prog: Progress, only: list[str] | None = None) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        set_state(s, r, "COLLECTING")
        secs = [o for o in outline(s, rid) if not only or o.key in only]
        base = {"lang": r.lang, "topic": r.topic or r.title}
        sections = [{"key": o.key, "title": o.title, "purpose": o.purpose, "required_inputs": o.required_inputs} for o in secs]
        links = list(r.links or [])
        web_ok = r.use_web is not False  # web research is on unless the author switched it off
        lang = r.lang
        info = {"description": r.description or "", "decision": r.decision_requested or "",
                "statements": [e.statement for e in s.query(Evidence).filter_by(report_id=rid, origin="user").limit(30).all()]}
        uploads = s.query(FileRow).filter(FileRow.report_id == rid, FileRow.role.in_(["source", "prior_report"])).all()
        known = {x.ref for x in s.query(Source).filter_by(report_id=rid).all()}
        known_parsed = [x.id for x in s.query(Source).filter_by(report_id=rid, status="parsed").all()]
    rnd = _Round(ctx, rid, prog, base, sections, lang)
    rnd.known_refs = known
    for sid in known_parsed:  # a rerun does not read again what is already parsed
        rnd.extracted.add(sid)
        rnd.origin_of.setdefault(sid, "document")
    kinds = ["files"] + [k for k in KINDS[1:] if ctx.connectors[k].available()]

    # 1. the author's own material first
    prog.update("reading", 0, 8, "Eigenes Material lesen")
    rnd.add_own(uploads, links)
    own = rnd.process()

    # 2. plan for this topic, with the own material known
    prog.update("planning", 2, 8, "Recherche planen")
    plan = _plan(ctx, rid, rnd, info, kinds, web_ok, "initial", 1, [])
    asked = [q["query"] for q in plan["queries"]]

    # 3. carry out the plan
    prog.update("searching", 3, 8, f"{len(plan['queries'])} Suchanfragen")
    stats = rnd.execute(plan)
    got = rnd.process()
    with ctx.db.session() as s:
        log_event(s, rid, "research_plan", round=1, mode="initial", strategy=plan.get("strategy", ""), needs=plan.get("needs", []), queries=plan["queries"],
                  result={**stats, "evidence_own": own, "evidence_new": got, "web": web_ok, "web_mode": rnd.web_mode, "web_note": rnd.web_note})

    # 4. gap rounds: what is still thin gets its own targeted search
    for n in range(2, 2 + max(0, ctx.settings.gap_rounds)):
        prog.update("gaps", 5, 8, "Lücken schließen")
        gap = _plan(ctx, rid, rnd, info, kinds, web_ok, "gaps", n, asked)
        if gap.get("enough") or not gap["queries"]:
            with ctx.db.session() as s:
                log_event(s, rid, "research_plan", round=n, mode="gaps", strategy=gap.get("strategy", ""), needs=gap.get("needs", []), queries=[], result={"enough": True})
            break
        asked += [q["query"] for q in gap["queries"]]
        stats = rnd.execute(gap)
        got = rnd.process()
        with ctx.db.session() as s:
            log_event(s, rid, "research_plan", round=n, mode="gaps", strategy=gap.get("strategy", ""), needs=gap.get("needs", []), queries=gap["queries"], result={**stats, "evidence_new": got})
    with ctx.db.session() as s:
        log_event(s, rid, "collected", sources=len(rnd.parsed), evidence=rnd.added, skipped_chunks=rnd.skipped_total)

    # 5. asset library
    prog.update("assets", 6, 8, "Bilder prüfen und Diagramme lesen")
    stats = assets_svc.assess(ctx, rid, base, sections)
    assets_svc.chart_evidence(ctx, rid, sections)
    prog.update("assets", 7, 8, "Bilder und Tabellen auswählen")
    assets_svc.curate(ctx, rid, base, sections)
    prog.update("collected", 8, 8, f"{rnd.added} Belege gefunden")
