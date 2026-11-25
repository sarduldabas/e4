"""Reading one document completely: code first, then the vision model for what code cannot read, then a quality check."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor

from ..core.ingest import Options, Parsed, apply_vision, parse_bytes
from .ctx import Context
from .runner import AgentCallFailed

VISION_BATCH = 4  # pages per call


def _data_url(jpeg: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(jpeg).decode()


def read_document(ctx: Context, rid: str, name: str, data: bytes, lang: str = "de") -> tuple[Parsed, dict]:
    """Parse `data`, send unreadable pages and pictures to the vision model, and return the document with a quality report."""
    parsed = parse_bytes(name, data, Options(max_vision_pages=ctx.settings.max_vision_pages))
    vinfo = resolve_vision(ctx, rid, parsed, name, lang)
    return parsed, quality_report(parsed, vinfo)


def resolve_vision(ctx: Context, rid: str, parsed: Parsed, name: str, lang: str) -> dict:
    tasks = list(parsed.vision)
    info = {"vision_pages": len(tasks), "vision_calls": 0, "vision_mode": None, "unread": [], "low_legibility": [], "failed_calls": 0}
    if not tasks:
        return info
    batches = [tasks[i:i + VISION_BATCH] for i in range(0, len(tasks), VISION_BATCH)]

    def call(batch):
        payload = {"lang": lang, "file_name": name, "pages": [{"key": t.key, "locator": t.locator, "reason": t.reason, "hint": t.hint[:200],
                                                              "existing_text": t.existing_text, "image": _data_url(t.image)} for t in batch]}
        try:
            return batch, ctx.runner.run_env("document-reader", payload, report_id=rid)
        except AgentCallFailed as e:
            return batch, e

    results: dict[str, dict] = {}
    with ThreadPoolExecutor(max_workers=max(1, ctx.settings.parallel_calls)) as pool:
        for batch, env in pool.map(call, batches):
            info["vision_calls"] += 1
            if isinstance(env, Exception):
                info["failed_calls"] += 1
                info["unread"] += [t.locator for t in batch if t.reason != "figure"]
                continue
            info["vision_mode"] = env.get("mode") if info["vision_mode"] in (None, env.get("mode")) else "mixed"
            by_key = {p["key"]: p for p in env["output"]["pages"]}
            for t in batch:
                res = by_key.get(t.key) or {}
                if env.get("mode") == "rules" and t.reason != "garbled":
                    if t.reason != "figure":
                        info["unread"].append(t.locator)
                    continue
                if (res.get("legibility") or 0) < 0.45 and t.reason in ("scanned", "garbled", "image"):
                    info["low_legibility"].append(t.locator)
                results[t.key] = res
    apply_vision(parsed, results)
    return info


def quality_report(p: Parsed, v: dict) -> dict:
    chars = sum(len(c.text) for c in p.chunks)
    warnings = list(p.warnings)
    if v["unread"]:
        why = "kein Vision-Modell verfügbar" if v["vision_mode"] == "rules" else "Vision-Modell nicht erreichbar" if v["failed_calls"] else "nicht lesbar"
        warnings.append(f"{len(v['unread'])} Seite(n)/Bild(er) nicht gelesen ({why}): {', '.join(v['unread'][:8])}{' …' if len(v['unread']) > 8 else ''}")
    if v["low_legibility"]:
        warnings.append(f"schlecht lesbar (bitte prüfen): {', '.join(v['low_legibility'][:8])}")
    pages = p.stats.get("pages") or p.stats.get("slides") or p.stats.get("sheets")
    if chars < 40:
        status = "poor"
        warnings.append("kein lesbarer Text gefunden")
    elif v["unread"] or v["low_legibility"] or any("limit" in w or "stopped" in w or "only the first" in w for w in warnings):
        status = "partial"
    else:
        status = "ok"
    return {"status": status, "chars": chars, "chunks": len(p.chunks), "pages": pages, "vision_pages": v["vision_pages"], "vision_mode": v["vision_mode"],
            "unread": v["unread"][:30], "low_legibility": v["low_legibility"][:30], "warnings": warnings[:25], "stats": p.stats, "properties": p.meta}


def preflight(name: str, data: bytes) -> dict:
    """What can be said about a file the moment it is uploaded, by code alone (no model call): its type, size of content and what will need the vision model."""
    try:
        p = parse_bytes(name, data, Options(max_vision_pages=10_000))
    except Exception as e:  # noqa: BLE001
        return {"status": "poor", "chars": 0, "chunks": 0, "warnings": [f"{e.__class__.__name__}: {str(e)[:160]}"], "preflight": True}
    chars = sum(len(c.text) for c in p.chunks)
    tasks = [t for t in p.vision if t.reason != "figure"]
    status = "poor" if chars < 40 and not p.vision else "pending" if tasks else "ok"
    return {"status": status, "chars": chars, "chunks": len(p.chunks), "pages": p.stats.get("pages") or p.stats.get("slides") or p.stats.get("sheets"), "vision_pages": len(tasks),
            "figures": len(p.vision) - len(tasks), "warnings": p.warnings[:10], "stats": p.stats, "properties": p.meta, "preflight": True}
