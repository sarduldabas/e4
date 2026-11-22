"""Stage 2, first half: find, screen, read and extract. Code does the fetching and parsing; agents do the judging."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from ..core.connectors import KINDS
from ..core.parsers import parse_bytes, thumbnail_data_url
from ..core.storage import safe_name
from ..models import Asset, Evidence, FileRow, Source
from .ctx import Context, get_report, log_event, outline, set_state
from .jobs import Progress

MAX_CHUNKS_PER_SOURCE = 120
BATCH = 25
MAX_IMAGES_PER_SOURCE = 12


def _read_source(ctx: Context, src: Source) -> tuple[str, bytes | str]:
    if src.kind == "web":
        url, html = ctx.web.fetch(src.ref)
        return url, html
    if src.file_id:
        with ctx.db.session() as s:
            f = s.get(FileRow, src.file_id)
        return f.name, ctx.store.get(f.key)
    return ctx.connectors[src.kind].fetch(src.ref)


def run_collect(ctx: Context, rid: str, prog: Progress, only: list[str] | None = None) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        set_state(s, r, "COLLECTING")
        secs = [o for o in outline(s, rid) if not only or o.key in only]
        base = {"lang": r.lang, "topic": r.topic or r.title}
        sections = [{"key": o.key, "title": o.title, "purpose": o.purpose, "required_inputs": o.required_inputs} for o in secs]
        links = list(r.links or [])
        user_statements = [e.statement for e in s.query(Evidence).filter_by(report_id=rid, origin="user").limit(30).all()]
        uploads = s.query(FileRow).filter(FileRow.report_id == rid, FileRow.role.in_(["source", "prior_report"])).all()
        known_refs = {x.ref for x in s.query(Source).filter_by(report_id=rid).all()}

    # 1. plan
    prog.update("planning", 0, 6, "Quellen planen")
    kinds = ["files"] + [k for k in KINDS[1:] if ctx.connectors[k].available()]
    allow_web = ctx.settings.allow_web and bool(links)
    plan = ctx.runner.run("source-planner", {**base, "description": "", "sections": sections, "user_statements": user_statements[:20],
                                             "available_kinds": kinds + (["web"] if allow_web else []), "allow_web": allow_web}, report_id=rid)

    # 2. search: uploads are always candidates, connectors are searched with the planned queries
    prog.update("searching", 1, 6, f"{len(plan['queries'])} Suchanfragen")
    cands: list[dict] = []
    with ctx.db.session() as s:
        for f in uploads:
            ref = f"upload:{f.id}"
            if ref not in known_refs:
                src = Source(report_id=rid, kind="files", title=f.name.rsplit(".", 1)[0], ref=ref, file_id=f.id, status="candidate")
                s.add(src)
                known_refs.add(ref)
        for url in links:
            if allow_web and url not in known_refs:
                s.add(Source(report_id=rid, kind="web", title=url[:120], ref=url, status="candidate"))
                known_refs.add(url)
        s.flush()
        excerpt: dict[str, tuple[str, str | None]] = {}
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
                excerpt[src.id] = (h.excerpt, h.modified)
        for src in s.query(Source).filter_by(report_id=rid, status="candidate").all():
            cands.append({"id": src.id, "title": src.title, "kind": src.kind, "path": src.ref if not src.ref.startswith("upload:") else None,
                          "modified": src.modified, "excerpt": excerpt.get(src.id, ("", None))[0]})
    # 3. screen
    prog.update("screening", 2, 6, f"{len(cands)} Kandidaten bewerten")
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
                src.reason = "vom Nutzer angegeben" if base["lang"] == "de" else "provided by the user"

    # 4. read
    with ctx.db.session() as s:
        todo = [(x.id, x.kind, x.title) for x in s.query(Source).filter_by(report_id=rid, status="selected").all()]
    prog.update("reading", 3, 6, f"{len(todo)} Quellen lesen")
    parsed_ids, web_pages = [], []
    for sid, kind, title in todo:
        try:
            with ctx.db.session() as s:
                src = s.get(Source, sid)
            name, data = _read_source(ctx, src)
            if kind == "web":
                from ..core.parsers import _html
                p = _html(str(data).encode("utf-8"))
                p.kind = "html"
            else:
                p = parse_bytes(name, data)
            chunks = [{"locator": c.locator, "text": c.text} for c in p.chunks]
            key = f"reports/{rid}/parsed/{sid}.json"
            ctx.store.put(key, json.dumps({"title": p.title, "kind": p.kind, "chunks": chunks}, ensure_ascii=False).encode("utf-8"))
            with ctx.db.session() as s:
                src = s.get(Source, sid)
                src.status, src.parsed_key, src.chunk_count, src.error = "parsed", key, len(chunks), None
                if kind == "web" and p.title:
                    src.title = p.title[:200]
                for n, im in enumerate(p.images[:MAX_IMAGES_PER_SOURCE]):
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
            if kind == "web":
                web_pages.append({"id": sid, "url": src.ref, "title": p.title or title, "text": "\n".join(c["text"] for c in chunks)[:9000]})
        except Exception as e:  # noqa: BLE001  one unreadable file must not stop the run
            with ctx.db.session() as s:
                src = s.get(Source, sid)
                src.status, src.error = "failed", f"{e.__class__.__name__}: {e}"[:280]
                log_event(s, rid, "source_failed", source=src.title, error=str(e)[:200])

    # 5. extract evidence
    jobs = []
    for sid in parsed_ids:
        if sid in {w["id"] for w in web_pages}:
            continue
        with ctx.db.session() as s:
            src = s.get(Source, sid)
        data = json.loads(ctx.store.get(src.parsed_key))
        chunks = data["chunks"][:MAX_CHUNKS_PER_SOURCE]
        for i in range(0, len(chunks), BATCH):
            jobs.append((sid, src.title, chunks[i:i + BATCH]))
    prog.update("extracting", 4, 6, f"{len(jobs)} Abschnitte auswerten")

    def extract(job):
        sid, title, chunks = job
        return sid, ctx.runner.run("evidence-extractor", {**base, "sections": sections, "document_id": sid, "document_name": title, "chunks": chunks}, report_id=rid)

    added = 0
    with ThreadPoolExecutor(max_workers=max(1, ctx.settings.parallel_sections)) as pool:
        results = list(pool.map(extract, jobs))
    with ctx.db.session() as s:
        have = {(e.section_key, e.statement.lower()) for e in s.query(Evidence).filter_by(report_id=rid).all()}
        for sid, out in results:
            for it in out["items"]:
                sig = (it["section_key"], it["statement"].lower())
                if sig in have:
                    continue
                have.add(sig)
                added += 1
                s.add(Evidence(report_id=rid, section_key=it["section_key"], origin="document", source_id=sid, kind=it["kind"], statement=it["statement"], quote=it["quote"],
                               locator=it["locator"], value=it.get("value"), unit=it.get("unit"), confidence=it.get("confidence", 0.7)))
        if web_pages:
            out = ctx.runner.run("web-researcher", {**base, "sections": sections, "pages": web_pages}, report_id=rid)
            for f in out["findings"]:
                sig = (f["section_key"], f["summary"].lower())
                if sig in have:
                    continue
                have.add(sig)
                added += 1
                s.add(Evidence(report_id=rid, section_key=f["section_key"], origin="web", source_id=f["page_id"], kind="fact", statement=f["summary"], quote=f["quote"],
                               locator="Web", confidence=round(0.4 + 0.4 * f["relevance"], 2)))
        log_event(s, rid, "collected", sources=len(parsed_ids), evidence=added)

    # 6. assets
    prog.update("assets", 5, 6, "Bilder und Tabellen auswählen")
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
    prog.update("collected", 6, 6, f"{added} Belege gefunden")
