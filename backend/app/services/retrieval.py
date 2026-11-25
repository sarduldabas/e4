"""Finding the passages that matter: a small BM25 over the parsed chunks of a report. Plain code, no model, no extra packages."""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass

STOP = set("""der die das den dem des ein eine einer eines einem einen und oder aber nicht mit von für auf aus bei nach über unter zum zur im in an am als auch bis
durch ist sind war wird werden wurde wurden hat haben kann können soll sollen wir sie es er ich ihr sich wie was wer wo wenn dass daß noch nur sehr mehr
the a an and or but not with of for on at from by to in is are was were be been has have can could should would we you it he she they this that these those as
also than then there their its into per ca bzw sowie""".split())
_WORD = re.compile(r"[a-zäöüß0-9]{3,}")


def tokens(text: str) -> list[str]:
    return [w[:6] for w in _WORD.findall(text.lower()) if w not in STOP]


@dataclass
class Passage:
    id: str  # "<source id>#<n>"
    source_id: str
    source_title: str
    locator: str
    text: str


class Index:
    def __init__(self, passages: list[Passage]):
        self.passages = passages
        self._tf = [Counter(tokens(p.text)) for p in passages]
        self._len = [sum(c.values()) or 1 for c in self._tf]
        self._avg = sum(self._len) / max(len(self._len), 1)
        df: Counter[str] = Counter()
        for c in self._tf:
            df.update(c.keys())
        n = max(len(passages), 1)
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokens(query)
        out = []
        for i, tf in enumerate(self._tf):
            s = 0.0
            for t in q:
                f = tf.get(t, 0)
                if f:
                    s += self._idf.get(t, 0.0) * (f * 2.2) / (f + 1.2 * (0.25 + 0.75 * self._len[i] / self._avg))
            out.append(s)
        return out

    def top(self, query: str, budget_chars: int, *, neighbours: bool = True, exclude: set[str] | None = None) -> list[Passage]:
        """The best passages for a query up to a character budget, each with its neighbour (a table row's header, the sentence before a figure)."""
        sc = self.scores(query)
        order = sorted(range(len(sc)), key=lambda i: -sc[i])
        chosen: list[int] = []
        used = 0
        seen: set[int] = set()
        for i in order:
            if sc[i] <= 0 or used >= budget_chars:
                break
            for j in ([i - 1, i, i + 1] if neighbours else [i]):
                if 0 <= j < len(self.passages) and j not in seen and self.passages[j].source_id == self.passages[i].source_id:
                    if exclude and self.passages[j].id in exclude:
                        continue
                    seen.add(j)
                    chosen.append(j)
                    used += len(self.passages[j].text)
        return [self.passages[j] for j in sorted(seen)]


def load_passages(ctx, rid: str) -> list[Passage]:
    """All parsed chunks of all parsed sources of the report, as passages with stable ids."""
    from ..models import Source

    out: list[Passage] = []
    with ctx.db.session() as s:
        rows = s.query(Source).filter(Source.report_id == rid, Source.status == "parsed").all()
        srcs = [(x.id, x.title, x.parsed_key) for x in rows if x.parsed_key]
    for sid, title, key in srcs:
        try:
            data = json.loads(ctx.store.get(key))
        except Exception:  # noqa: BLE001
            continue
        for n, c in enumerate(data.get("chunks", [])):
            out.append(Passage(f"{sid}#{n}", sid, title, c["locator"], c["text"]))
    return out


def select_for_extraction(chunks: list[dict], sections: list[dict], topic: str, budget: int) -> tuple[list[dict], int]:
    """A huge source is read completely when it fits the budget; otherwise the chunks that fit the outline best come first. Returns (chunks in order, skipped count)."""
    total = sum(len(c["text"]) for c in chunks)
    if total <= budget:
        return chunks, 0
    query = topic + " " + " ".join(f"{s['title']} {s.get('purpose', '')} {' '.join(s.get('required_inputs', []))}" for s in sections)
    idx = Index([Passage(str(i), "", "", c["locator"], c["text"]) for i, c in enumerate(chunks)])
    sc = idx.scores(query)
    # numbers and tables carry the figures an analysis needs
    for i, c in enumerate(chunks):
        sc[i] += 0.3 * min(len(re.findall(r"\d[\d.,]*", c["text"])), 10) / 10
    keep, used = set(), 0
    for i in sorted(range(len(chunks)), key=lambda i: -sc[i]):
        if used + len(chunks[i]["text"]) > budget:
            continue
        keep.add(i)
        used += len(chunks[i]["text"])
    return [c for i, c in enumerate(chunks) if i in keep], len(chunks) - len(keep)
