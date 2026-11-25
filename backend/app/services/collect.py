"""Stage 2, first half: find, screen, read completely and extract. Code does the fetching and parsing, the vision model reads
what code cannot read, agents do the judging. Nothing that fits in the budget is left unread."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor

from ..core.connectors import KINDS
from ..core.parsers import thumbnail_data_url
from ..core.storage import safe_name
from ..models import Asset, Evidence, FileRow, Source
from .ctx import Context, get_report, log_event, outline, set_state
from .ingest import read_document
from .jobs import Progress
from .retrieval import select_for_extraction

MAX_IMAGES_PER_SOURCE = 12
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


def _web_search(ctx: Context, rid: str, base: dict, sections: list[dict], plan: dict, existing: set[str]) -> tuple[list[tuple[str, dict]], list[str], str | None]:
    """Searches the public web for the planned web queries. Returns (briefings as (source id, parsed doc), cited urls, note)."""
    queries = [q for q in plan["queries"] if q["kind"] == "web"][:8]
    if not queries:
        return [], [], None
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
            src = Source(report_id=rid, kind="web", title=("Websuche: " + q["query"])[:290], ref=ref, status="selected", relevance=0.6, section_keys=res["section_keys"],
                         reason="Websuche (Foundry)")
            s.add(src)
            s.flush()
            existing.add(ref)
            body = res["briefing"].strip()
            cites = "\n".join(f"- {x['title'] or x['url']} — {x['url']}" for x in res["sources"])
            doc = {"title": src.title, "kind": "search", "chunks": [{"locator": f"Websuche „{q['query']}“", "text": body + (f"\n\nQuellen:\n{cites}" if cites else "")}]}
            docs.append((src.id, doc))
            urls += [x["url"] for x in res["sources"]]
    return docs, urls, note


def run_collect(ctx: Context, rid: str, prog: Progress, only: list[str] | None = None) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        set_state(s, r, "COLLECTING")
        secs = [o for o in outline(s, rid) if not only or o.key in only]
        base = {"lang": r.lang, "topic": r.topic or r.title}
        sections = [{"key": o.key, "title": o.title, "purpose": o.purpose, "required_inputs": o.required_inputs} for o in secs]
        links = list(r.links or [])
        use_web = bool(r.use_web)
        lang = r.lang
        user_statements = [e.statement for e in s.query(Evidence).filter_by(report_id=rid, origin="user").limit(30).all()]
        uploads = s.query(FileRow).filter(FileRow.report_id == rid, FileRow.role.in_(["source", "prior_report"])).all()
        known_refs = {x.ref for x in s.query(Source).filter_by(report_id=rid).all()}

    # 1. plan
    prog.update("planning", 0, 7, "Quellen planen")
    kinds = ["files"] + [k for k in KINDS[1:] if ctx.connectors[k].available()]
    web_ok = use_web or bool(links)
    plan = ctx.runner.run("source-planner", {**base, "description": "", "sections": sections, "user_statements": user_statements[:20],
                                             "available_kinds": kinds + (["web"] if web_ok else []), "allow_web": web_ok}, report_id=rid)

    # 2. search: uploads are always candidates, connectors are searched with the planned queries, the web with the search tool
    prog.update("searching", 1, 7, f"{len(plan['queries'])} Suchanfragen")
    cands: list[dict] = []
    with ctx.db.session() as s:
        for f in uploads:
            ref = f"upload:{f.id}"
            if ref not in known_refs:
                s.add(Source(report_id=rid, kind="files", title=f.name.rsplit(".", 1)[0], ref=ref, file_id=f.id, status="candidate"))
                known_refs.add(ref)
        for url in links:
            if ctx.settings.allow_web and url not in known_refs:
                s.add(Source(report_id=rid, kind="web", title=url[:120], ref=url, status="candidate"))
                known_refs.add(url)
        s.flush()
        excerpt: dict[str, str] = {}
        for q in plan["queries"]:
            conn = ctx.connectors.get(q["kind"])
            if not conn:
                continue
            for h in conn.search(q["query"]):
                if h.ref in known_refs:
                    continue
                src = Source(report_id=rid, kind=h.kind, title=h.title, ref=h.ref, modified=h.modified, status="candidate")
                s.add(src)
                s.flush()
                known_refs.add(h.ref)
                excerpt[src.id] = h.excerpt
        for src in s.query(Source).filter_by(report_id=rid, status="candidate").all():
            cands.append({"id": src.id, "title": src.title, "kind": src.kind, "path": src.ref if not src.ref.startswith("upload:") else None,
                          "modified": src.modified, "excerpt": excerpt.get(src.id, "")})

    web_docs: list[tuple[str, dict]] = []
    web_note = None
    if use_web:
        try:
            web_docs, cited, web_note = _web_search(ctx, rid, base, sections, plan, known_refs)
        except Exception as e:  # noqa: BLE001  a failed search must not stop the report
            cited, web_note = [], f"Websuche fehlgeschlagen: {e}"[:300]
        if cited and ctx.settings.allow_web:
            with ctx.db.session() as s:
                for url in cited:
                    if url not in known_refs and len(known_refs) < 10_000 and s.query(Source).filter_by(report_id=rid, kind="web").count() < MAX_WEB_PAGES + len(links) + len(web_docs):
                        s.add(Source(report_id=rid, kind="web", title=url[:200], ref=url, status="selected", reason="von der Websuche zitiert"))
                        known_refs.add(url)
        if web_note:
            with ctx.db.session() as s:
                log_event(s, rid, "web_search_note", note=web_note)

    # 3. screen
    prog.update("screening", 2, 7, f"{len(cands)} Kandidaten bewerten")
    decisions: dict[str, dict] = {}
    if cands:
        out = ctx.runner.run("source-screener", {**base, "sections": sections, "candidates": cands}, report_id=rid)
        decisions = {d["candidate_id"]: d for d in out["decisions"]}
    with ctx.db.session() as s:
        for src in s.query(Source).filter_by(report_id=rid, status="candidate").all():
            d = decisions.get(src.id)
            mine = bool(src.file_id) or src.kind == "web"  # what the user attached or named is always read
            if d:
                src.relevance, src.section_keys, src.reason, src.duplicate_of = d["relevance"], d["section_keys"], d["reason"], d["duplicate_of"]
            src.status = "selected" if (mine or (d and d["include"])) else "rejected"
            if mine and d and not d["include"]:
                src.reason = "vom Nutzer angegeben" if lang == "de" else "provided by the user"

    # 4. read: completely; what code cannot read goes to the vision model
    with ctx.db.session() as s:
        todo = [(x.id, x.kind, x.title, x.ref) for x in s.query(Source).filter_by(report_id=rid, status="selected").all()]
    prog.update("reading", 3, 7, f"{len(todo)} Quellen lesen")
    parsed_ids: list[str] = []
    origin_of: dict[str, str] = {}
    cap_of: dict[str, float] = {}

    def store_doc(sid: str, doc: dict, info: dict | None) -> None:
        key = f"reports/{rid}/parsed/{sid}.json"
        ctx.store.put(key, json.dumps(doc, ensure_ascii=False).encode("utf-8"))
        with ctx.db.session() as s:
            src = s.get(Source, sid)
            src.status, src.parsed_key, src.chunk_count, src.error, src.info = "parsed", key, len(doc["chunks"]), None, info

    for sid, doc in web_docs:
        store_doc(sid, doc, {"status": "ok", "chars": sum(len(c["text"]) for c in doc["chunks"]), "chunks": len(doc["chunks"]), "warnings": [], "origin": "web-search"})
        parsed_ids.append(sid)
        origin_of[sid], cap_of[sid] = "web", CAP_BY_KIND["search"]

    for sid, kind, title, ref in todo:
        try:
            with ctx.db.session() as s:
                src = s.get(Source, sid)
            name, data = _read_source(ctx, src)
            p, info = read_document(ctx, rid, name, data, lang)
            doc = {"title": p.title, "kind": p.kind, "chunks": [{"locator": c.locator, "text": c.text} for c in p.chunks]}
            store_doc(sid, doc, info)
            with ctx.db.session() as s:
                src = s.get(Source, sid)
                if kind == "web" and p.title:
                    src.title = p.title[:200]
                if src.file_id:
                    f = s.get(FileRow, src.file_id)
                    if f:
                        f.info = info
                for im in p.images[:MAX_IMAGES_PER_SOURCE]:
                    if im.width and im.width < 120:
                        continue
                    a = Asset(report_id=rid, source_id=sid, kind="image", caption=im.caption or f"{src.title} – {im.locator}", width=im.width, height=im.height, context=f"{im.locator} {src.title}")
                    s.add(a)
                    s.flush()
                    a.key = ctx.store.put(f"reports/{rid}/assets/{a.id}-{safe_name('img.' + im.ext)}", im.data)
                for t in p.tables[:6]:
                    if len(t.rows) >= 2:
                        s.add(Asset(report_id=rid, source_id=sid, kind="table", caption=t.caption or t.locator, table=t.rows[:25], context=f"{t.locator} " + " ".join(" ".join(r) for r in t.rows[:3])[:400]))
            parsed_ids.append(sid)
            origin_of[sid] = "web" if kind == "web" else "document"
            cap_of[sid] = CAP_BY_KIND["page"] if kind == "web" else 1.0
        except Exception as e:  # noqa: BLE001  one unreadable file must not stop the run
            with ctx.db.session() as s:
                src = s.get(Source, sid)
                src.status, src.error = "failed", f"{e.__class__.__name__}: {e}"[:280]
                src.info = {"status": "failed", "warnings": [str(e)[:200]]}
                log_event(s, rid, "source_failed", source=src.title, error=str(e)[:200])

    # 5. extract evidence from everything that was read
    jobs: list[tuple[str, str, list[dict]]] = []
    skipped_total = 0
    for sid in parsed_ids:
        with ctx.db.session() as s:
            src = s.get(Source, sid)
            title, key = src.title, src.parsed_key
        data = json.loads(ctx.store.get(key))
        chunks, skipped = select_for_extraction(data["chunks"], sections, base["topic"], ctx.settings.max_extract_chars)
        if skipped:
            skipped_total += skipped
            with ctx.db.session() as s:
                src = s.get(Source, sid)
                info = dict(src.info or {})
                info["warnings"] = list(info.get("warnings", [])) + [f"{skipped} von {len(data['chunks'])} Abschnitten nicht ausgewertet (Umfang); die relevantesten zuerst gelesen"]
                info["status"] = "partial" if info.get("status") == "ok" else info.get("status")
                src.info = info
        for b in _batches(chunks, ctx.settings.extract_batch_chars):
            jobs.append((sid, title, b))
    prog.update("extracting", 4, 7, f"{len(jobs)} Textabschnitte auswerten")

    def extract(job):
        sid, title, chunks = job
        try:
            return sid, ctx.runner.run("evidence-extractor", {**base, "sections": sections, "document_id": sid, "document_name": title, "chunks": chunks, "max_items": 80}, report_id=rid), None
        except Exception as e:  # noqa: BLE001  the other batches continue
            return sid, None, f"{e.__class__.__name__}: {e}"[:200]

    with ThreadPoolExecutor(max_workers=max(1, ctx.settings.parallel_calls)) as pool:
        results = list(pool.map(extract, jobs))

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
                s.add(Evidence(report_id=rid, section_key=it["section_key"], origin=origin_of[sid], source_id=sid, kind=it["kind"], statement=it["statement"], quote=it["quote"],
                               locator=it["locator"][:300], value=it.get("value"), unit=it.get("unit"), entity=it.get("entity"), period=it.get("period"),
                               confidence=min(it.get("confidence", 0.7), cap_of[sid])))
        log_event(s, rid, "collected", sources=len(parsed_ids), evidence=added, skipped_chunks=skipped_total)

    # 6. assets
    prog.update("assets", 5, 7, "Bilder und Tabellen auswählen")
    with ctx.db.session() as s:
        fresh = s.query(Asset).filter(Asset.report_id == rid, Asset.section_key.is_(None), Asset.chosen.is_(False)).limit(40).all()
        cand = []
        for a in fresh:
            src = s.get(Source, a.source_id) if a.source_id else None
            c = {"id": a.id, "kind": a.kind, "caption": a.caption, "context": a.context[:500], "source_label": src.title if src else "", "width": a.width, "height": a.height}
            if a.kind == "image" and a.key and len([x for x in cand if x.get("data_url")]) < 8:
                c["data_url"] = thumbnail_data_url(ctx.store.get(a.key))
            cand.append(c)
    if cand:
        out = ctx.runner.run("asset-curator", {**base, "sections": sections, "candidates": cand}, report_id=rid)
        with ctx.db.session() as s:
            for ch in out["chosen"]:
                a = s.get(Asset, ch["asset_id"])
                if a:
                    a.section_key, a.chosen, a.score, a.caption = ch["section_key"], True, ch["score"], ch["caption"] or a.caption
    prog.update("collected", 7, 7, f"{added} Belege gefunden")
