"""The deck as data: every slide is one spec (core/slides). The web page shows it, the PowerPoint file is built from it, edits change it."""
from __future__ import annotations

import copy

from ..core.slides import build_pptx, claim_ids_of, merge, normalise, numbers_not_in, pack_plan, parse_numbers, scrub, theme_of
from ..core.slides.spec import block_numbers
from . import assets as assets_svc
from ..models import Asset, Calculation, Claim, Deck, DeckSnapshot, Evidence, FileRow, Flag, Report, SectionDraft, Slide, Source
from .ctx import Context, NotFound, StateError, current_claims, draft_of, get_report, log_event, outline, require_state
from .numbers import allowed_numbers, section_numbers

SYSTEM_ORDER = {"_title": -3, "_summary": -2, "_decision": 10**6, "_sources": 10**6 + 1, "_changes": 10**6 + 2}
LOCKED_KINDS = ("sources", "changes")
HISTORY = 20


def _t(lang: str, de: str, en: str) -> str:
    return de if lang == "de" else en


def order_map(s, rid: str) -> dict[str, int]:
    return {**{o.key: o.position for o in outline(s, rid)}, **SYSTEM_ORDER}


def ordered(s, rid: str, ver: int) -> list[Slide]:
    om = order_map(s, rid)
    rows = [x for x in s.query(Slide).filter_by(report_id=rid, version_no=ver).all() if x.section_key in om]
    rows.sort(key=lambda x: (om[x.section_key], x.position))
    return rows


def legacy(spec: dict) -> tuple[list[dict], dict | None, list[str]]:
    """The older flat fields of a slide (bullets, chart, asset ids), derived from its spec."""
    bullets, chart, assets = [], None, []
    for b in spec["blocks"]:
        if b["type"] == "bullets":
            bullets += [{"text": i["text"], "claim_ids": i["claim_ids"]} for i in b["items"]]
        elif b["type"] == "chart" and chart is None:
            c = b["chart"]
            chart = {"type": c["type"], "title": c["title"], "unit": c["unit"], "labels": c["labels"], "values": c["series"][0]["values"]}
        elif b["type"] == "image":
            assets.append(b["asset_id"])
    return bullets, chart, assets


class Ledger:
    """Claims, evidence and sources of one version, loaded once: used to write source lines and to check numbers."""

    def __init__(self, s, rid: str, ver: int):
        self.claims = {c.id: c for c in s.query(Claim).filter_by(report_id=rid, version_no=ver).all()}
        self.ev = {e.id: e for e in s.query(Evidence).filter_by(report_id=rid).all()}
        self.srcs = {x.id: x for x in s.query(Source).filter_by(report_id=rid).all()}
        self.calcs = {k.id: k for k in s.query(Calculation).filter_by(report_id=rid, version_no=ver).all()}

    def label(self, e: Evidence, lang: str) -> str:
        if e.origin == "user":
            return _t(lang, "Angabe des Autors", "Author's input")
        return self.srcs[e.source_id].title if e.source_id in self.srcs else ""

    def refs(self, claim_ids: list[str], lang: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for cid in claim_ids:
            c = self.claims.get(cid)
            for eid in (c.evidence_ids if c else []):
                e = self.ev.get(eid)
                if e:
                    r = (self.label(e, lang), e.locator or "")
                    if r[0] and r not in out:
                        out.append(r)
        return out

    def evidence_lines(self, claim_ids: list[str], lang: str) -> list[str]:
        lines: list[str] = []
        for cid in claim_ids:
            c = self.claims.get(cid)
            for eid in (c.evidence_ids if c else [])[:3]:
                e = self.ev.get(eid)
                if e:
                    lab = self.label(e, lang)
                    lines.append(f"- {e.statement} [{lab}{', ' + e.locator if e.locator else ''}]")
        return list(dict.fromkeys(lines))


def finish(led: Ledger, spec: dict, lang: str, *, keep_notes: bool = True) -> tuple[dict, list[str]]:
    """Normalises a spec and writes its source line and evidence list from the claims it cites."""
    spec, warnings = normalise(spec, lang)
    ids = claim_ids_of(spec)
    refs = led.refs(ids, lang)
    spec["source_line"] = (_t(lang, "Quellen: ", "Sources: ") + "; ".join(f"{a}{' (' + b + ')' if b else ''}" for a, b in refs[:3]) + (" …" if len(refs) > 3 else ""))[:400] if refs else ""
    spec["evidence"] = led.evidence_lines(ids, lang)[:40]
    return spec, warnings


def put(s, rid: str, ver: int, section_key: str, position: int, spec: dict, *, user_edited: bool = False) -> Slide:
    bullets, chart, assets = legacy(spec)
    row = Slide(report_id=rid, version_no=ver, section_key=section_key, position=position, title=spec["title"][:300], bullets=bullets, chart=chart, asset_ids=assets,
                notes=spec.get("notes", ""), layout=spec["layout"], spec=spec, kind=spec.get("kind", "content"), history=[], user_edited=user_edited)
    s.add(row)
    return row


def refresh_system_slides(ctx: Context, rid: str) -> None:
    """Title and sources slides follow the content: recomputed whenever slides are generated or edited."""
    with ctx.db.session() as s:
        r = get_report(s, rid)
        ver, lang = r.version_no, r.lang
        led = Ledger(s, rid, ver)
        body = [x for x in ordered(s, rid, ver) if x.section_key not in SYSTEM_ORDER or x.section_key in ("_summary", "_decision")]
        used: dict[str, set[str]] = {}
        for x in body:
            for label, loc in led.refs(claim_ids_of(x.spec or {"blocks": []}), lang):
                used.setdefault(label, set()).add(loc)
        def upsert(key: str, spec: dict | None) -> None:
            row = s.query(Slide).filter_by(report_id=rid, version_no=ver, section_key=key).first()
            if spec is None:
                if row:
                    s.delete(row)
                return
            if row is None:
                put(s, rid, ver, key, 0, spec)
            elif not row.user_edited:  # an edited title slide is the author's
                bullets, chart, assets = legacy(spec)
                row.spec, row.title, row.bullets, row.chart, row.asset_ids, row.layout, row.kind = spec, spec["title"][:300], bullets, chart, assets, spec["layout"], spec.get("kind", "content")

        date = ".".join(reversed(r.date.split("-"))) if lang == "de" and len(r.date) == 10 and r.date[4] == "-" else r.date
        upsert("_title", normalise({"kind": "title", "title": r.title, "subtitle": " · ".join(x for x in [r.committee, date, r.version] if x)}, lang)[0])
        rows = [[k, ", ".join(sorted(v - {""})) or "–"] for k, v in sorted(used.items())][:10]
        upsert("_sources", normalise({"kind": "sources", "layout": "table", "title": _t(lang, "Quellenverzeichnis", "Sources"), "blocks": [
            {"slot": "table", "type": "table", "header": [_t(lang, "Quelle", "Source"), _t(lang, "Fundstellen", "Locations")], "rows": rows}]}, lang)[0] if used else None)


def packed(s, rid: str, ver: int, lang: str, rows: list[Slide], specs: list[dict]) -> tuple[list[dict], list[list[int]]]:
    """The slides as the file has them: short text slides of neighbouring sections share a page (core/slides/pack.py). Also returns the groups of slide indexes."""
    sections = [x.section_key for x in rows]
    groups = pack_plan(specs, sections)
    if all(len(g) == 1 for g in groups):
        return specs, groups
    led = Ledger(s, rid, ver)
    titles = {o.key: o.title for o in outline(s, rid)}
    out = []
    for g in groups:
        if len(g) == 1:
            out.append(specs[g[0]])
        else:
            merged, _ = finish(led, merge([specs[i] for i in g], [titles.get(sections[i], sections[i]) for i in g]), lang)
            out.append(merged)
    return out, groups


def deck_specs(ctx: Context, rid: str) -> tuple[list[dict], dict[str, bytes], bytes | None, str]:
    """(specs in order, image bytes by asset id, template bytes, language): everything the PowerPoint file is built from."""
    with ctx.db.session() as s:
        r = get_report(s, rid)
        lang = r.lang
        rows = ordered(s, rid, r.version_no)
        specs = [normalise(x.spec, lang)[0] if x.spec else normalise({"layout": "bullets", "title": x.title, "blocks": [{"slot": "bullets", "type": "bullets", "items": x.bullets}]}, lang)[0] for x in rows]
        specs, _ = packed(s, rid, r.version_no, lang, rows, specs)
        assets = {a.id: a for a in s.query(Asset).filter_by(report_id=rid).all()}
        images = {}
        for sp in specs:
            for b in sp["blocks"]:
                a = assets.get(b.get("asset_id")) if b["type"] == "image" else None
                if a and a.key:
                    images[a.id] = ctx.store.get(a.key)
        tpl = s.query(FileRow).filter_by(report_id=rid, role="template").order_by(FileRow.created_at.desc()).first()
        tpl_bytes = ctx.store.get(tpl.key) if tpl else None
    return specs, images, tpl_bytes, lang


def build_deck_file(ctx: Context, rid: str) -> dict:
    refresh_system_slides(ctx, rid)
    specs, images, tpl, lang = deck_specs(ctx, rid)
    data = build_pptx(specs, template=tpl, lang=lang, images=images)
    with ctx.db.session() as s:
        r = get_report(s, rid)
        ver = r.version_no
        key = f"reports/{rid}/decks/v{ver}.pptx"
        ctx.store.put(key, data)
        old = s.query(Deck).filter_by(report_id=rid, version_no=ver).first()
        changes = old.changes if old else []
        storyline = old.storyline if old else None
        if old:
            s.delete(old)
            s.flush()
        s.add(Deck(report_id=rid, version_no=ver, key=key, slide_count=len(specs), changes=changes, storyline=storyline))
    return {"key": key, "slides": len(specs)}


# ---------------------------------------------------------------------------------------------- reading
def _claim_view(c: Claim, led: Ledger, lang: str) -> dict:
    return {"id": c.id, "text": c.text, "status": c.status, "verdict": c.verdict, "issues": c.issues,
            "evidence": [{"id": e.id, "statement": e.statement, "quote": e.quote, "locator": e.locator, "source": led.label(e, lang), "origin": e.origin}
                         for e in (led.ev.get(i) for i in c.evidence_ids) if e][:6],
            "calculations": [{"id": k.id, "label": k.label, "formula": k.formula, "value": k.value, "unit": k.unit} for k in (led.calcs.get(i) for i in c.calc_ids) if k]}


def attention(s, rid: str, ver: int, slides: list[dict], titles: dict[str, str]) -> list[dict]:
    """What the author may want to look at: claims the verifier left out of the slides, and open flags. Nothing here blocks the download."""
    first: dict[str, str] = {}
    by_claim: dict[str, str] = {}
    for x in slides:
        first.setdefault(x["section_key"], x["id"])
        for c in x["claims"]:
            by_claim.setdefault(c["id"], x["id"])
    items: list[dict] = []
    left_out = s.query(Claim).filter_by(report_id=rid, version_no=ver, status="flagged").order_by(Claim.section_key, Claim.position).all()
    ids = {c.id for c in left_out}
    for c in left_out:
        items.append({"kind": "claim", "id": c.id, "severity": "warning", "text": c.text, "issues": c.issues, "section_key": c.section_key,
                      "section": titles.get(c.section_key, c.section_key), "slide_id": first.get(c.section_key)})
    for f in s.query(Flag).filter_by(report_id=rid, version_no=ver, status="open").order_by(Flag.created_at).all():
        if f.severity not in ("blocker", "warning") or (f.claim_id and f.claim_id in ids):
            continue
        items.append({"kind": "flag", "id": f.id, "severity": f.severity, "text": f.text, "issues": [], "origin": f.origin, "section_key": f.section_key,
                      "section": titles.get(f.section_key or "", ""), "slide_id": by_claim.get(f.claim_id or "") or first.get(f.section_key or "")})
    items.sort(key=lambda i: (i["severity"] != "blocker", i["kind"] != "claim"))
    return items


def deck_view(ctx: Context, rid: str) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        ver, lang = r.version_no, r.lang
        titles = {o.key: o.title for o in outline(s, rid)}
        led = Ledger(s, rid, ver)
        d = s.query(Deck).filter_by(report_id=rid, version_no=ver).first()
        tpl = s.query(FileRow).filter_by(report_id=rid, role="template").first()
        rows = ordered(s, rid, ver)
        specs = [normalise(x.spec or {"layout": "bullets", "title": x.title, "blocks": [{"slot": "bullets", "type": "bullets", "items": x.bullets}]}, lang)[0] for x in rows]
        _, groups = packed(s, rid, ver, lang, rows, specs)
        joins = {g[k] for g in groups for k in range(len(g) - 1)}  # a slide that shares its page with the next one in the file
        flags = s.query(Flag).filter_by(report_id=rid, version_no=ver, status="open").all()
        sys_titles = {"_title": _t(lang, "Titel", "Title"), "_summary": _t(lang, "Management Summary", "Executive summary"), "_decision": _t(lang, "Beschluss", "Decision"),
                      "_sources": _t(lang, "Quellen", "Sources")}
        slides = []
        for n, (x, spec) in enumerate(zip(rows, specs), 1):
            ids = claim_ids_of(spec)
            slides.append({"id": x.id, "n": n, "section_key": x.section_key, "section": titles.get(x.section_key) or sys_titles.get(x.section_key, x.section_key),
                           "kind": x.kind, "locked": x.kind in LOCKED_KINDS, "title": x.title, "spec": spec, "bullets": x.bullets, "chart": x.chart, "notes": x.notes, "asset_ids": x.asset_ids,
                           "user_edited": x.user_edited, "can_undo": bool(x.history), "shares_with_next": (n - 1) in joins,
                           "claims": [_claim_view(led.claims[cid], led, lang) for cid in ids if cid in led.claims],
                           "attention": sum(1 for f in flags if f.claim_id in ids and f.severity in ("blocker", "warning"))})
        undo = s.query(DeckSnapshot).filter_by(report_id=rid).order_by(DeckSnapshot.created_at.desc()).first()
        return {"version": r.version, "state": r.state, "has_file": bool(d), "slides": slides, "theme": theme_of(ctx.store.get(tpl.key) if tpl else None),
                "template": tpl.name if tpl else None, "attention": attention(s, rid, ver, slides, titles), "export": {"slides": len(groups), "shared": sum(1 for g in groups if len(g) > 1)},
                "ai_undo": {"label": undo.label} if undo else None}


# ---------------------------------------------------------------------------------------------- editing
def _slide(s, rid: str, sid: str, ver: int) -> Slide:
    x = s.get(Slide, sid)
    if not x or x.report_id != rid or x.version_no != ver:
        raise NotFound(sid)
    return x


def _push(x: Slide) -> None:
    x.history = (list(x.history or []) + [copy.deepcopy(x.spec)])[-HISTORY:]


def _apply(x: Slide, spec: dict) -> None:
    bullets, chart, assets = legacy(spec)
    x.spec, x.title, x.bullets, x.chart, x.asset_ids, x.notes, x.layout = spec, spec["title"][:300], bullets, chart, assets, spec.get("notes", ""), spec["layout"]
    x.user_edited = True


def _number_warnings(led: Ledger, spec: dict, lang: str, extra: list[float] = ()) -> list[str]:
    allowed = allowed_numbers(list(led.claims.values()), led.ev, led.calcs) + list(extra)
    bad = numbers_not_in(spec, allowed)
    return [(_t(lang, f"Die Zahl {b} steht in keiner belegten Aussage.", f"The number {b} is not in any verified claim.")) for b in bad]


def patch_slide(ctx: Context, rid: str, sid: str, *, title: str | None = None, bullets: list[str] | None = None, spec: dict | None = None) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW")
        x = _slide(s, rid, sid, r.version_no)
        if x.kind in LOCKED_KINDS:
            raise StateError("this slide is generated from the other slides and can not be edited")
        led = Ledger(s, rid, r.version_no)
        cur = copy.deepcopy(x.spec) if x.spec else normalise({"layout": "bullets", "title": x.title, "blocks": []}, r.lang)[0]
        new = copy.deepcopy(spec) if spec is not None else cur
        if title is not None and title.strip():
            new["title"] = title.strip()
        if bullets is not None:  # the older way: the bullets of the first text block, claim links kept by position
            blk = next((b for b in new["blocks"] if b["type"] == "bullets"), None)
            if blk is None:
                blk = {"slot": "bullets", "type": "bullets", "items": []}
                new["blocks"].append(blk)
            old = blk["items"]
            blk["items"] = [{"text": t.strip(), "claim_ids": old[i]["claim_ids"] if i < len(old) else []} for i, t in enumerate(b for b in bullets if b.strip())]
        new.setdefault("kind", cur.get("kind", "content"))
        new, warnings = finish(led, new, r.lang)
        _push(x)
        _apply(x, new)
        warnings = _number_warnings(led, new, r.lang) + warnings
        log_event(s, rid, "slide_edited", slide=sid, warnings=len(warnings))
    build_deck_file(ctx, rid)
    return {"id": sid, "warnings": warnings, "spec": new}


def revise_slide(ctx: Context, rid: str, sid: str, instruction: str) -> dict:
    """A reviewer's comment on one slide, carried out by the slide-editor agent and checked against the ledger."""
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW")
        x = _slide(s, rid, sid, r.version_no)
        if x.kind in LOCKED_KINDS:
            raise StateError("this slide is generated from the other slides and can not be edited")
        lang, ver, key = r.lang, r.version_no, x.section_key
        led = Ledger(s, rid, ver)
        approved = [c for c in current_claims(s, rid, ver, None if key.startswith("_") else key, ("approved",))]
        d = draft_of(s, rid, key, ver) if not key.startswith("_") else None
        charts = d.charts if d else []
        assets = assets_svc.slide_assets(s, rid, key) if not key.startswith("_") else []
        titles = [y.title for y in ordered(s, rid, ver) if y.id != sid][:30]
        payload = {"lang": lang, "topic": r.topic or r.title, "slide": x.spec, "instruction": instruction.strip()[:2000],
                   "claims": [{"id": c.id, "text": c.text, "kind": c.kind} for c in approved], "numbers": section_numbers(approved, led.ev, led.calcs, lang),
                   "charts": charts, "assets": [{"id": a.id, "kind": a.kind, "caption": a.caption, "table": a.table} for a in assets], "other_titles": titles}
        before = copy.deepcopy(x.spec)
    env = ctx.runner.run_env("slide-editor", payload, report_id=rid)
    out = env["output"]
    with ctx.db.session() as s:
        r = get_report(s, rid)
        led = Ledger(s, rid, r.version_no)
        x = _slide(s, rid, sid, r.version_no)
        new, warnings = finish(led, {**out["slide"], "kind": x.kind}, lang)
        allowed = allowed_numbers(list(led.claims.values()), led.ev, led.calcs) + parse_numbers(instruction) + [v for b in before["blocks"] for v in block_numbers(b)]
        new, removed = scrub(new, allowed, lang)
        new, _ = finish(led, {**new, "kind": x.kind}, lang)
        needs = list(out.get("needs", [])) + [_t(lang, f"Nicht übernommen (Zahl nicht in den Belegen): {m}", f"Not applied (number not in the evidence): {m}") for m in removed]
        changed = new != before
        if changed:
            _push(x)
            _apply(x, new)
            log_event(s, rid, "slide_revised", slide=sid, mode=env.get("mode"), instruction=instruction[:200])
    if changed:
        build_deck_file(ctx, rid)
    return {"id": sid, "changed": changed, "summary": out.get("summary", ""), "needs": needs, "mode": env.get("mode"), "spec": new, "warnings": warnings}


def undo_slide(ctx: Context, rid: str, sid: str) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW")
        x = _slide(s, rid, sid, r.version_no)
        if not x.history:
            raise StateError("nothing to undo")
        hist = list(x.history)
        prev = hist.pop()
        _apply(x, prev)
        x.history = hist
        x.user_edited = bool(hist)
        log_event(s, rid, "slide_undo", slide=sid)
    build_deck_file(ctx, rid)
    return {"id": sid, "spec": prev}


def add_slide(ctx: Context, rid: str, after: str | None, layout: str) -> dict:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW")
        ver, lang = r.version_no, r.lang
        rows = ordered(s, rid, ver)
        ref = next((y for y in rows if y.id == after), None)
        key = ref.section_key if ref and not ref.section_key.startswith("_") else (next((y.section_key for y in reversed(rows) if not y.section_key.startswith("_")), None))
        if not key:
            raise StateError("there is no section to add the slide to")
        pos = (ref.position + 1) if ref and ref.section_key == key else 10_000
        for y in rows:
            if y.section_key == key and y.position >= pos:
                y.position += 1
        led = Ledger(s, rid, ver)
        spec, _ = finish(led, {"layout": layout, "title": _t(lang, "Neue Folie", "New slide"), "blocks": [{"slot": "bullets", "type": "bullets", "items": [{"text": _t(lang, "Text eingeben", "Enter text")}]}] if layout != "table" else []}, lang)
        row = put(s, rid, ver, key, pos, spec, user_edited=True)
        s.flush()
        sid = row.id
        log_event(s, rid, "slide_added", slide=sid)
    build_deck_file(ctx, rid)
    return {"id": sid}


def delete_slide(ctx: Context, rid: str, sid: str) -> None:
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW")
        x = _slide(s, rid, sid, r.version_no)
        if x.kind in ("title",) or x.kind in LOCKED_KINDS:
            raise StateError("this slide can not be deleted")
        s.delete(x)
        log_event(s, rid, "slide_deleted", slide=sid)
    build_deck_file(ctx, rid)


def move_slide(ctx: Context, rid: str, sid: str, index: int) -> None:
    """Moves a content slide to position `index` (0-based) among the slides; it joins the section of the slide before it."""
    with ctx.db.session() as s:
        r = get_report(s, rid)
        require_state(r, "DECK_REVIEW")
        ver = r.version_no
        rows = ordered(s, rid, ver)
        x = _slide(s, rid, sid, ver)
        if x.section_key.startswith("_"):
            raise StateError("this slide can not be moved")
        rows.remove(x)
        lo = next((i for i, y in enumerate(rows) if y.section_key not in ("_title", "_summary")), 0)
        hi = next((i for i, y in enumerate(rows) if y.section_key in ("_decision", "_sources", "_changes")), len(rows))
        index = max(lo, min(index, hi))
        rows.insert(index, x)
        neighbour = next((y for y in reversed(rows[:index]) if not y.section_key.startswith("_")), None) or next((y for y in rows[index + 1:] if not y.section_key.startswith("_")), None)
        x.section_key = neighbour.section_key if neighbour else x.section_key
        by_section: dict[str, int] = {}
        for y in rows:
            if y.section_key.startswith("_"):
                continue
            y.position = by_section.get(y.section_key, 0)
            by_section[y.section_key] = y.position + 1
        # the sections follow the order of their first slide
        seen: list[str] = []
        for y in rows:
            if not y.section_key.startswith("_") and y.section_key not in seen:
                seen.append(y.section_key)
        sec = {o.key: o for o in outline(s, rid)}
        for i, k in enumerate(seen):
            if k in sec:
                sec[k].position = i
        rest = [o for o in sec.values() if o.key not in seen]
        for j, o in enumerate(rest):
            o.position = len(seen) + j
        log_event(s, rid, "slide_moved", slide=sid, index=index)
    build_deck_file(ctx, rid)
