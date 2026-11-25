"""The figures a slide may show: taken from the approved claims' evidence and from calculations done in code, never made up."""
from __future__ import annotations

from ..core.slides import parse_numbers
from ..models import Calculation, Claim, Evidence


def fmt(v: float, lang: str = "de") -> str:
    """12.0 -> '12' ; 15.2 -> '15,2' ; 1250 -> '1.250' (de) / '1,250' (en). At most two decimals."""
    s = f"{v:,.2f}".rstrip("0").rstrip(".")
    if lang == "de":
        s = s.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")
    return s


def _clip(t: str, n: int) -> str:
    t = " ".join((t or "").split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def section_numbers(claims: list[Claim], ev: dict[str, Evidence], calcs: dict[str, Calculation], lang: str, limit: int = 40) -> list[dict]:
    """Number objects (see agents/app/agents/slides_common.py) for the claims of one section."""
    out: dict[str, dict] = {}
    for c in claims:
        for cid in c.calc_ids:
            k = calcs.get(cid)
            if k and k.value is not None:
                n = out.setdefault(k.id, {"ref": k.id, "label": _clip(k.label, 90), "text": fmt(k.value, lang), "value": float(k.value), "unit": k.unit, "entity": None, "period": None, "claim_ids": [], "calc_ids": [k.id]})
                n["claim_ids"].append(c.id)
        for eid in c.evidence_ids:
            e = ev.get(eid)
            if e and e.value is not None:
                lab = _clip(e.statement, 90)
                if e.entity and e.entity.lower() not in lab.lower():
                    lab = f"{e.entity}: {lab}"
                n = out.setdefault(e.id, {"ref": e.id, "label": lab, "text": fmt(e.value, lang), "value": float(e.value), "unit": e.unit, "entity": e.entity, "period": e.period, "claim_ids": [], "calc_ids": []})
                n["claim_ids"].append(c.id)
    rows = sorted(out.values(), key=lambda n: (not n["calc_ids"], -len(n["claim_ids"])))
    return rows[:limit]


def allowed_numbers(claims: list[Claim], ev: dict[str, Evidence], calcs: dict[str, Calculation]) -> list[float]:
    """Every figure that may appear on a slide: in an approved claim, in the evidence it cites, or computed from it."""
    vals: set[float] = set()
    for c in claims:
        vals.update(parse_numbers(c.text))
        for cid in c.calc_ids:
            k = calcs.get(cid)
            if k and k.value is not None:
                vals.add(float(k.value))
        for eid in c.evidence_ids:
            e = ev.get(eid)
            if e:
                if e.value is not None:
                    vals.add(float(e.value))
                vals.update(parse_numbers(e.quote))
                vals.update(parse_numbers(e.statement))
    return sorted(vals)
