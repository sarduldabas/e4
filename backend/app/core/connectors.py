"""Source connectors. On the PC each kind is a local folder (data/connectors/<kind>); in production the same
interface is implemented against SharePoint, Exchange, Teams, SAP and the web. Connectors only find and fetch.
They never interpret: that is the agents' job."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from .parsers import SUPPORTED, kind_of, parse_bytes

KINDS = ["files", "sharepoint", "mail", "teams", "sap"]
_WORD = re.compile(r"[^\W_]{3,}")


def words(text: str) -> set[str]:
    return {w[:6] for w in _WORD.findall((text or "").lower())}


@dataclass
class Hit:
    title: str
    kind: str
    ref: str  # absolute path (local) or url
    modified: str | None
    excerpt: str
    size: int
    score: float = 0.0


class LocalFolderConnector:
    def __init__(self, kind: str, root: Path):
        self.kind, self.root = kind, Path(root)
        self._cache: dict[tuple[str, float], str] = {}

    def available(self) -> bool:
        return self.root.is_dir() and any(self.root.rglob("*"))

    def _excerpt(self, p: Path) -> str:
        key = (str(p), p.stat().st_mtime)
        if key not in self._cache:
            try:
                parsed = parse_bytes(p.name, p.read_bytes())
                self._cache[key] = " ".join(c.text for c in parsed.chunks[:3])[:1500]
            except Exception:
                self._cache[key] = ""
        return self._cache[key]

    def search(self, query: str, limit: int = 15) -> list[Hit]:
        q = words(query)
        hits = []
        for p in sorted(self.root.rglob("*")):
            if not p.is_file() or kind_of(p.name) not in SUPPORTED or p.name.startswith(("~$", ".")):
                continue
            ex = self._excerpt(p)
            name_words, text_words = words(p.stem.replace("_", " ")), words(ex)
            score = (2 * len(q & name_words) + len(q & text_words)) / max(len(q), 1)
            if score <= 0:
                continue
            st = p.stat()
            hits.append(Hit(p.stem, self.kind, str(p), dt.date.fromtimestamp(st.st_mtime).isoformat(), ex[:400], st.st_size, round(score, 3)))
        return sorted(hits, key=lambda h: -h.score)[:limit]

    def fetch(self, ref: str) -> tuple[str, bytes]:
        p = Path(ref).resolve()
        if self.root.resolve() not in p.parents:
            raise ValueError("outside the connector folder")
        return p.name, p.read_bytes()


class WebFetcher:
    """Fetches public pages named by the user. Off unless ALLOW_WEB=true."""

    def __init__(self, allow: bool, timeout: float = 15.0):
        self.allow, self.timeout = allow, timeout

    def fetch(self, url: str) -> tuple[str, str]:
        if not self.allow:
            raise PermissionError("web access is switched off (ALLOW_WEB=false)")
        import httpx
        if not re.match(r"^https?://", url):
            raise ValueError("only http(s) links")
        host = re.sub(r"^https?://([^/:]+).*", r"\1", url).lower()
        if host in ("localhost", "127.0.0.1", "::1") or host.endswith((".local", ".internal")) or re.match(r"^(10|192\.168|172\.(1[6-9]|2\d|3[01]))\.", host):
            raise PermissionError("internal addresses are not fetched")
        r = httpx.get(url, timeout=self.timeout, follow_redirects=True, headers={"User-Agent": "COE4-Committee-Assistant/0.1"})
        r.raise_for_status()
        if len(r.content) > 3_000_000:
            raise ValueError("page too large")
        return url, r.text
