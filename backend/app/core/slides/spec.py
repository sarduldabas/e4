"""The slide specification: the one JSON document that the web page shows and the PowerPoint file is built from.

A slide is {layout, title, blocks[], notes, ...}. A layout (layouts.json) names slots with a position on a 1280x720 canvas; each block sits in
one slot. `normalise` makes any input valid (unknown layout, wrong slot, too many items, text that does not fit) and computes the font sizes, so that
the renderers only draw. Numbers are checked against the ledger by `numbers_not_in` before a generated slide is accepted.
"""
from __future__ import annotations

import copy
import json
import re
from functools import lru_cache
from pathlib import Path

from . import fit

HERE = Path(__file__).parent
SLOT_TYPES = {"kpis": "kpis", "chart": "chart", "bullets": "bullets", "bullets2": "bullets", "table": "table", "callout": "callout", "image": "image"}
CHART_TYPES = ("column", "bar", "line", "donut", "stacked")


@lru_cache(maxsize=1)
def layouts() -> dict:
    return json.loads((HERE / "layouts.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def default_theme() -> dict:
    return json.loads((HERE / "theme.json").read_text(encoding="utf-8"))


def _s(x, n: int) -> str:
    return re.sub(r"[ \t]+", " ", str(x if x is not None else "")).strip()[:n]


def _ids(x) -> list[str]:
    return [str(i) for i in (x or []) if i][:12]


def _num(x) -> float | None:
    try:
        v = float(x)
        return v if v == v and abs(v) < 1e15 else None
    except (TypeError, ValueError):
        return None


def _block(raw: dict, slot: str, lim: dict, box: dict, warnings: list[str]) -> dict | None:
    t = SLOT_TYPES[slot]
    if raw.get("type") != t:
        return None
    if t == "bullets":
        items = []
        for it in (raw.get("items") or [])[: lim[slot]]:
            it = {"text": it} if isinstance(it, str) else it
            text = _s(it.get("text"), lim["bullet_chars"])
            if text:
                items.append({"text": text, "claim_ids": _ids(it.get("claim_ids")), "level": 1 if it.get("level") == 1 else 0})
        if not items:
            return None
        size, ok = fit.bullets_size([i["text"] for i in items], box["w"], box["h"])
        if not ok:
            warnings.append(f"{slot}: text too long for the box")
        return {"type": t, "slot": slot, "items": items, "size": size}
    if t == "kpis":
        ks = []
        for k in (raw.get("items") or [])[: lim["kpis"]]:
            value, label = _s(k.get("value"), 14), _s(k.get("label"), 60)
            if value and label:
                ks.append({"value": value, "unit": _s(k.get("unit"), 12), "label": label, "delta": _s(k.get("delta"), 18) or None,
                           "tone": k.get("tone") if k.get("tone") in ("up", "down", "neutral") else "neutral", "claim_ids": _ids(k.get("claim_ids")), "calc_ids": _ids(k.get("calc_ids"))})
        if not ks:
            return None
        vs, ls = fit.kpi_sizes(len(ks), box["w"], [(k["value"], k["unit"], k["label"]) for k in ks])
        return {"type": t, "slot": slot, "items": ks, "size": vs, "label_size": ls}
    if t == "chart":
        c = raw.get("chart") or raw
        labels = [_s(x, 40) for x in (c.get("labels") or [])][:12]
        series = []
        for s in (c.get("series") or []):
            vals = [_num(v) for v in (s.get("values") or [])][: len(labels)]
            if len(vals) == len(labels) and all(v is not None for v in vals):
                series.append({"name": _s(s.get("name"), 40), "values": vals})
        ctype = c.get("type") if c.get("type") in CHART_TYPES else "column"
        if ctype == "donut" and series:
            series = series[:1]
        if not labels or not series or (ctype == "donut" and any(v < 0 for v in series[0]["values"])):
            return None
        hl = c.get("highlight")
        return {"type": t, "slot": slot, "chart": {"type": ctype, "title": _s(c.get("title"), 120), "unit": _s(c.get("unit"), 20), "labels": labels, "series": series[:4],
                                                    "highlight": hl if isinstance(hl, int) and 0 <= hl < len(labels) else None}, "claim_ids": _ids(raw.get("claim_ids")), "calc_ids": _ids(raw.get("calc_ids"))}
    if t == "table":
        header = [_s(x, 40) for x in (raw.get("header") or [])][: lim["table_cols"]]
        rows = [[_s(x, 90) for x in r][: lim["table_cols"]] for r in (raw.get("rows") or [])][: lim["table_rows"]]
        rows = [r for r in rows if any(r)]
        if not rows:
            return None
        cols = max([len(header)] + [len(r) for r in rows])
        header = header + [""] * (cols - len(header)) if header else []
        rows = [r + [""] * (cols - len(r)) for r in rows]
        size, widths, ok = fit.table_size(header, rows, box["w"], box["h"])
        if not ok:
            warnings.append("table: too many lines for the box")
        hr = raw.get("highlight_row")
        return {"type": t, "slot": slot, "header": header, "rows": rows, "size": size, "widths": [round(w, 1) for w in widths],
                "highlight_row": hr if isinstance(hr, int) and 0 <= hr < len(rows) else None, "claim_ids": _ids(raw.get("claim_ids")), "calc_ids": _ids(raw.get("calc_ids")),
                "caption": _s(raw.get("caption"), 120)}
    if t == "callout":
        text, title = _s(raw.get("text"), lim["callout_chars"]), _s(raw.get("title"), 80)
        if not text:
            return None
        size, ok = fit.callout_size(title, text, box["w"], box["h"])
        if not ok:
            warnings.append("callout: text too long for the box")
        return {"type": t, "slot": slot, "title": title, "text": text, "tone": raw.get("tone") if raw.get("tone") in ("info", "decision", "warn", "good") else "info", "size": size, "claim_ids": _ids(raw.get("claim_ids"))}
    if t == "image":
        if not raw.get("asset_id"):
            return None
        return {"type": t, "slot": slot, "asset_id": str(raw["asset_id"]), "caption": _s(raw.get("caption"), 160)}
    return None


def normalise(spec: dict, lang: str = "de") -> tuple[dict, list[str]]:
    """A valid slide from any input. Returns (spec, warnings); warnings name what was cut or does not fit."""
    L = layouts()
    warnings: list[str] = []
    name = spec.get("layout") if spec.get("layout") in L["layouts"] else "bullets"
    lay = L["layouts"][name]
    lim = {**L["limits"]}
    title = _s(spec.get("title"), lim["title_chars"]) or "—"
    tsize, ok = fit.title_size(title, L["title_box"]["w"], L["title_box"]["h"])
    if not ok:
        warnings.append("title: too long")
    blocks, used = [], set()
    for raw in spec.get("blocks") or []:
        slot = raw.get("slot")
        if slot not in lay["slots"] or slot in used:
            continue
        b = _block(raw, slot, lim, lay["slots"][slot], warnings)
        if b:
            blocks.append(b)
            used.add(slot)
    blocks.sort(key=lambda b: list(lay["slots"]).index(b["slot"]))
    out = {"layout": name, "kind": spec.get("kind") if spec.get("kind") in ("title", "summary", "content", "decision", "sources", "changes") else "content",
           "title": title, "title_size": tsize, "blocks": blocks, "notes": _s(spec.get("notes"), 1800), "source_line": _s(spec.get("source_line"), 400),
           "evidence": [_s(x, 320) for x in (spec.get("evidence") or [])][:40]}
    if spec.get("kind") == "title":
        out.update({"layout": "title", "subtitle": _s(spec.get("subtitle"), 200), "blocks": []})
    return out, warnings


def block_numbers(b: dict) -> list[float]:
    """The numbers a block shows: what must come from the ledger."""
    out: list[float] = []
    if b["type"] == "chart":
        for s in b["chart"]["series"]:
            out += s["values"]
    elif b["type"] in ("kpis", "bullets", "table", "callout"):
        texts = []
        if b["type"] == "kpis":
            texts = [k["value"] for k in b["items"]]
        elif b["type"] == "bullets":
            texts = [i["text"] for i in b["items"]]
        elif b["type"] == "table":
            texts = [c for r in b["rows"] for c in r]
        else:
            texts = [b["text"]]
        for t in texts:
            out += parse_numbers(t)
    return out


_NUM = re.compile(r"(?<![\w.])[-+]?\d{1,3}(?:[.  ]\d{3})+(?:,\d+)?|[-+]?\d+(?:[.,]\d+)?")


def parse_numbers(text: str) -> list[float]:
    out = []
    for m in _NUM.findall(text or ""):
        t = m.replace(" ", "").replace(" ", "")
        if re.fullmatch(r"[-+]?\d{1,3}(\.\d{3})+(,\d+)?", t):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", ".")
        try:
            out.append(float(t))
        except ValueError:
            pass
    return out


def numbers_not_in(spec: dict, allowed: list[float]) -> list[str]:
    """Numbers shown on the slide that no evidence, calculation or claim contains. Years, small counts and list numbers are not checked."""
    bad: list[str] = []
    for b in spec["blocks"]:
        for v in block_numbers(b):
            if abs(v - round(v)) < 1e-9 and (1900 <= v <= 2100 or abs(v) <= 12):
                continue
            if _is_bad([v], allowed):
                bad.append(f"{v:g}")
    return bad


def _is_bad(values: list[float], allowed: list[float]) -> list[str]:
    bad = []
    for v in values:
        if abs(v - round(v)) < 1e-9 and (1900 <= v <= 2100 or abs(v) <= 12):
            continue
        if not any(abs(v - a) <= 1e-6 * max(1.0, abs(a)) or (abs(a) >= 1 and abs(v - a) <= 0.0051 * (1 if abs(a) < 100 else 10) and round(a, 1) == round(v, 1)) for a in allowed):
            bad.append(f"{v:g}")
    return bad


def scrub(spec: dict, allowed: list[float], lang: str = "de") -> tuple[dict, list[str]]:
    """Removes what shows a number the ledger does not contain: single bullets and key figures, whole tables, charts and callouts."""
    removed: list[str] = []
    blocks = []
    for b in spec["blocks"]:
        if b["type"] == "bullets":
            keep = []
            for it in b["items"]:
                bad = _is_bad(parse_numbers(it["text"]), allowed)
                (removed.append(f"{', '.join(bad)}: {it['text'][:50]}") if bad else keep.append(it))
            if keep:
                blocks.append({**b, "items": keep})
        elif b["type"] == "kpis":
            keep = []
            for it in b["items"]:
                bad = _is_bad(parse_numbers(it["value"]), allowed)
                (removed.append(f"{', '.join(bad)}: {it['label'][:50]}") if bad else keep.append(it))
            if keep:
                blocks.append({**b, "items": keep})
        else:
            bad = _is_bad(block_numbers(b), allowed) if b["type"] in ("chart", "table", "callout") else []
            if bad:
                removed.append(f"{', '.join(bad)}: {b['type']}")
            else:
                blocks.append(b)
    return normalise({**spec, "blocks": blocks})[0], removed


def claim_ids_of(spec: dict) -> list[str]:
    ids: list[str] = []
    for b in spec["blocks"]:
        if b["type"] == "bullets":
            for i in b["items"]:
                ids += i["claim_ids"]
        elif b["type"] == "kpis":
            for i in b["items"]:
                ids += i["claim_ids"]
        else:
            ids += b.get("claim_ids", [])
    return list(dict.fromkeys(ids))


def copy_spec(spec: dict) -> dict:
    return copy.deepcopy(spec)
