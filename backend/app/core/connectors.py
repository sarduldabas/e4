"""Source connectors. On the PC each kind is a local folder (data/connectors/<kind>); in production the same
interface is implemented against SharePoint, Exchange, Teams, SAP and the web. Connectors only find and fetch.
They never interpret: that is the agents' job."""
from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass
from pathlib import Path

from .parsers import SUPPORTED, kind_of, parse_bytes

KINDS = ["files", "sharepoint", "mail", "teams", "sap", "jira", "confluence"]
# What each source kind is good for. The research planner reads this to decide, per topic, where to look. A new connector (a real
# Jira or Confluence client, say) needs an entry here and a class with `available()`, `search()` and `fetch()`; nothing else changes.
CATALOG = {
    "files": {"label": "Uploaded files", "description": "Documents the author attached to this report: offers, protocols, presentations, spreadsheets, mails, scans.",
              "query_style": "2-6 keywords in the documents' own vocabulary"},
    "sharepoint": {"label": "SharePoint", "description": "Team sites and document libraries: previous committee papers, templates, offers, contracts, project documents, minutes.",
                   "query_style": "document title words, project or supplier names, document types (Vorlage, Protokoll, Angebot)"},
    "mail": {"label": "Mail", "description": "Mailbox: discussions, approvals, supplier correspondence, attachments sent around.", "query_style": "names, subject words, supplier or product"},
    "teams": {"label": "Teams", "description": "Chats and channel posts: day-to-day coordination, informal decisions, open questions of the project team.",
              "query_style": "project name, topic, person"},
    "sap": {"label": "SAP", "description": "Booked costs, budgets, purchase orders, cost centres and other financial master and transaction data.",
            "query_style": "cost centre, order, supplier, period"},
    "jira": {"label": "Jira", "description": "Tickets, epics, status, owners, due dates, blockers, defects and sprint progress of the project: how far the work really is.",
             "query_style": "project key, epic or component, status words (blocked, overdue), ticket topic"},
    "confluence": {"label": "Confluence", "description": "Wiki pages: specifications, architecture and decision records, requirements, meeting notes, how-tos and project documentation.",
                   "query_style": "page title words, space, decision or requirement topic"},
    "web": {"label": "Public web", "description": "Everything outside the company: market data, benchmarks, competitors, suppliers, prices, technology, regulation, recent news.",
            "query_style": "3-10 words with entity, metric and year, or one precise question"},
}
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

    def fetch_document(self, url: str, max_bytes: int = 25_000_000) -> tuple[str, bytes]:
        """A cited page or document (HTML, PDF, Office file) as bytes with a file name that tells the reader what it is."""
        import httpx
        from urllib.parse import urlparse

        self._check(url)
        r = httpx.get(url, timeout=max(self.timeout, 30.0), follow_redirects=True, headers={"User-Agent": "COE4-Committee-Assistant/0.1"})
        r.raise_for_status()
        self._check(str(r.url))  # a redirect must not lead to an internal address
        if len(r.content) > max_bytes:
            raise ValueError("document too large")
        ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
        name = Path(urlparse(str(r.url)).path).name or "seite"
        ext = {"application/pdf": ".pdf", "text/html": ".html", "application/xhtml+xml": ".html"}.get(ctype)
        if ext and not name.lower().endswith(ext):
            name = (name if "." not in name else name.rsplit(".", 1)[0]) + ext
        return name, r.content

    def page_images(self, html: bytes, base_url: str, limit: int = 6) -> list[dict]:
        """The main pictures of a fetched HTML page (figures with captions first), downloaded with the same checks as pages.
        Returns [{"data", "ext", "caption", "url"}]. Logos, icons, tracking pixels and tiny pictures are left out."""
        from html.parser import HTMLParser
        from urllib.parse import urljoin, urlparse

        class P(HTMLParser):
            def __init__(self):
                super().__init__()
                self.items: list[dict] = []
                self._fig = None
                self._cap = False

            def handle_starttag(self, tag, a):
                a = dict(a)
                if tag == "figure":
                    self._fig = {"caption": ""}
                if tag == "figcaption":
                    self._cap = True
                if tag == "img":
                    src = a.get("src") or (a.get("srcset", "").split(",")[0].strip().split(" ")[0] if a.get("srcset") else "") or a.get("data-src", "")
                    if src and not src.startswith("data:"):
                        self.items.append({"src": src, "alt": a.get("alt", ""), "w": a.get("width", ""), "h": a.get("height", ""), "fig": self._fig})
                if tag == "meta" and a.get("property") == "og:image" and a.get("content"):
                    self.items.append({"src": a["content"], "alt": "", "w": "", "h": "", "fig": None, "og": True})

            def handle_endtag(self, tag):
                if tag == "figure":
                    self._fig = None
                if tag == "figcaption":
                    self._cap = False

            def handle_data(self, data):
                if self._cap and self._fig is not None:
                    self._fig["caption"] += data

        parser = P()
        try:
            parser.feed(html.decode("utf-8", "replace"))
        except Exception:  # noqa: BLE001
            return []
        skip = re.compile(r"logo|icon|sprite|avatar|banner|tracking|pixel|spacer|button|badge|flag|emoji|\.svg($|\?)|\.gif($|\?)", re.I)
        seen, out = set(), []
        ranked = sorted(parser.items, key=lambda i: (0 if i["fig"] and i["fig"]["caption"].strip() else 1 if not i.get("og") else 2))
        for it in ranked:
            if len(out) >= limit:
                break
            url = urljoin(base_url, it["src"])
            if url in seen or skip.search(url) or not url.lower().startswith(("http://", "https://")):
                continue
            seen.add(url)
            try:
                if (it["w"].isdigit() and int(it["w"]) < 250) or (it["h"].isdigit() and int(it["h"]) < 120):
                    continue
                self._check(url)
                import httpx

                r = httpx.get(url, timeout=self.timeout, follow_redirects=True, headers={"User-Agent": "COE4-Committee-Assistant/0.1"})
                r.raise_for_status()
                self._check(str(r.url))
                ctype = r.headers.get("content-type", "").split(";")[0].strip().lower()
                if not ctype.startswith("image/") or ctype in ("image/svg+xml", "image/gif") or not (12_000 <= len(r.content) <= 6_000_000):
                    continue
                cap = " ".join(((it["fig"] or {}).get("caption", "") or it["alt"]).split())[:200]
                out.append({"data": r.content, "ext": {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}.get(ctype, "jpg"), "caption": cap, "url": url, "host": urlparse(url).netloc})
            except Exception:  # noqa: BLE001  a picture that cannot be fetched is skipped
                continue
        return out

    def _check(self, url: str) -> None:
        if not self.allow:
            raise PermissionError("web access is switched off (ALLOW_WEB=false)")
        if not re.match(r"^https?://", url):
            raise ValueError("only http(s) links")
        host = re.sub(r"^https?://([^/:]+).*", r"\1", url).lower()
        if host in ("localhost", "127.0.0.1", "::1") or host.endswith((".local", ".internal")) or re.match(r"^(10|192\.168|172\.(1[6-9]|2\d|3[01])|169\.254)\.", host):
            raise PermissionError("internal addresses are not fetched")
