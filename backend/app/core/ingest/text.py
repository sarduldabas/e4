"""Text handling shared by all readers: decoding, cleaning, cutting into chunks."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .model import Chunk

CHUNK_CHARS = 1800


def decode(data: bytes) -> str:
    if data[:3] == b"\xef\xbb\xbf":
        return data[3:].decode("utf-8", "replace")
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", "replace")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        from charset_normalizer import from_bytes

        best = from_bytes(data).best()
        if best is not None:
            return str(best)
    except Exception:  # noqa: BLE001
        pass
    return data.decode("cp1252", "replace")


_HYPHEN = re.compile(r"(?<=[a-zäöüß])-\n(?=[a-zäöüß])")
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(text: str) -> str:
    """Normalise what readers return: unicode form, control characters, hyphenated line breaks, runs of blanks."""
    t = unicodedata.normalize("NFC", text or "")
    t = _CTRL.sub(" ", t).replace(" ", " ").replace("​", "").replace("\r\n", "\n").replace("\r", "\n")
    t = _HYPHEN.sub("", t)
    t = re.sub(r"[ \t]+", " ", t)
    t = re.sub(r" *\n *", "\n", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def split(locator: str, text: str, ref: str | None = None, size: int = CHUNK_CHARS) -> list[Chunk]:
    """Long text is cut at paragraph borders (never inside a table row); each piece keeps the locator with a part number."""
    text = clean(text)
    if not text:
        return []
    if len(text) <= size:
        return [Chunk(locator, text, ref)]
    pieces: list[str] = []
    cur = ""
    for para in text.split("\n"):
        while len(para) > size * 1.5:  # a single enormous line: cut at a sentence or space
            cut = max(para.rfind(". ", 0, size), para.rfind(" ", 0, size))
            cut = cut + 1 if cut > size // 3 else size
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.append(para[:cut])
            para = para[cut:].lstrip()
        if cur and len(cur) + len(para) + 1 > size:
            pieces.append(cur)
            cur = ""
        cur += para + "\n"
    if cur.strip():
        pieces.append(cur)
    if len(pieces) == 1:
        return [Chunk(locator, pieces[0].strip(), ref)]
    return [Chunk(f"{locator} ({i})", p.strip(), ref) for i, p in enumerate(pieces, 1) if p.strip()]


def cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.10g}"
    return re.sub(r"\s+", " ", str(v)).strip()


def rows_to_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(c for c in r if c != "") for r in rows if any(c for c in r))


def strip_html(h: str) -> str:
    import html

    h = re.sub(r"(?is)<(script|style|nav|footer|header|noscript|svg)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?is)<!--.*?-->", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>|</table>", "\n", h)
    h = re.sub(r"(?i)</t[dh]>", " | ", h)
    h = re.sub(r"<[^>]+>", " ", h)
    return clean(html.unescape(h))


_PAGE_NO = re.compile(r"(?i)\b(seite|page|s\.)\s*\d+(\s*(von|of|/)\s*\d+)?|^\s*[-–]?\s*\d{1,4}\s*([-–]|/\s*\d{1,4})?\s*$")


def _header_key(line: str) -> str:
    """A line with its page number taken out. Only page numbers are neutralised: other digits stay, so body lines with different figures are never merged."""
    return _PAGE_NO.sub("#", line.strip())


def drop_repeated_lines(pages: list[str], min_pages: int = 4) -> list[str]:
    """Running headers, footers and page numbers repeat on most pages; they are noise for the analysis."""
    if len(pages) < min_pages:
        return pages
    counts: Counter[str] = Counter()
    for p in pages:
        lines = [l.strip() for l in p.split("\n") if l.strip()]
        for l in set(_header_key(x) for x in lines[:3] + lines[-3:]):
            counts[l] += 1
    noisy = {k for k, n in counts.items() if n >= max(3, int(len(pages) * 0.6)) and len(k) < 120}
    if not noisy:
        return pages
    return ["\n".join(l for l in p.split("\n") if _header_key(l) not in noisy) for p in pages]


def garbled_ratio(text: str) -> float:
    """Share of characters that look like a broken text layer: replacement characters, mojibake, symbols, no vowels."""
    t = text.strip()
    if len(t) < 40:
        return 0.0
    bad = t.count("�") + len(re.findall(r"Ã[\x80-\xbf¤¶¼Ÿ]|â€|Â[\xa0-\xbf]", t))
    letters = sum(ch.isalpha() for ch in t)
    odd = sum(1 for ch in t if not (ch.isalnum() or ch.isspace() or ch in ".,;:!?()[]{}%€$&/+-–—'\"“”„‚‘’°=<>#*@_|\\"))
    words = re.findall(r"[A-Za-zÄÖÜäöüß]{4,}", t)
    novowel = sum(1 for w in words if not re.search(r"[aeiouyäöü]", w.lower()))
    ratio = (bad * 6 + odd * 2) / len(t)
    if words:
        ratio += 0.8 * novowel / len(words) if novowel / len(words) > 0.25 else 0
    if letters / len(t) < 0.35 and len(t) > 200:
        ratio += 0.2
    return round(min(1.0, ratio), 3)
