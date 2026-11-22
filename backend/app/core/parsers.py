"""Reading files is code, not a language model: text, tables and images come out of the file exactly as they are in it."""
from __future__ import annotations

import csv
import email
import io
import re
from dataclasses import dataclass, field
from email import policy
from pathlib import Path

CHUNK_CHARS = 1800
TEXT_KINDS = {"txt", "md", "csv", "eml", "html", "htm", "json"}
SUPPORTED = TEXT_KINDS | {"docx", "pptx", "xlsx", "pdf", "png", "jpg", "jpeg"}


@dataclass
class Chunk:
    locator: str
    text: str


@dataclass
class Image:
    data: bytes
    ext: str
    width: int | None
    height: int | None
    caption: str
    locator: str


@dataclass
class Table:
    caption: str
    rows: list[list[str]]
    locator: str


@dataclass
class Parsed:
    kind: str
    chunks: list[Chunk] = field(default_factory=list)
    images: list[Image] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    title: str = ""


def kind_of(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def _split(locator: str, text: str) -> list[Chunk]:
    """Long text is cut at paragraph borders; each piece keeps the locator (with a part number)."""
    text = text.strip()
    if not text:
        return []
    if len(text) <= CHUNK_CHARS:
        return [Chunk(locator, text)]
    out, cur, n = [], "", 1
    for para in re.split(r"\n{2,}|\n", text):
        if cur and len(cur) + len(para) > CHUNK_CHARS:
            out.append(Chunk(f"{locator} ({n})", cur.strip()))
            cur, n = "", n + 1
        cur += para + "\n"
    if cur.strip():
        out.append(Chunk(f"{locator} ({n})" if n > 1 else locator, cur.strip()))
    return out


def _cell(v) -> str:
    if v is None:
        return ""
    if isinstance(v, float):
        return f"{v:.10g}"
    return str(v).strip()


def _rows_to_text(rows: list[list[str]]) -> str:
    return "\n".join(" | ".join(c for c in r if c != "") for r in rows if any(c for c in r))


def parse_bytes(name: str, data: bytes) -> Parsed:
    kind = kind_of(name)
    fn = {"txt": _text, "md": _text, "json": _text, "csv": _csv, "eml": _eml, "html": _html, "htm": _html, "docx": _docx, "pptx": _pptx,
          "xlsx": _xlsx, "pdf": _pdf, "png": _image, "jpg": _image, "jpeg": _image}.get(kind)
    if fn is None:
        raise ValueError(f"file type .{kind} is not supported")
    p = fn(data)
    p.kind, p.title = kind, p.title or Path(name).stem
    return p


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", "replace")


def _text(data: bytes) -> Parsed:
    t = _decode(data)
    chunks = []
    for i, block in enumerate(_split("Text", t), 1):
        chunks.append(block)
    return Parsed("txt", chunks)


def _csv(data: bytes) -> Parsed:
    text = _decode(data)
    try:
        dialect = csv.Sniffer().sniff(text[:2000], delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    rows = [[c.strip() for c in r] for r in csv.reader(io.StringIO(text), dialect)]
    p = Parsed("csv", tables=[Table("", rows[:60], "Tabelle")])
    for i in range(0, len(rows), 15):
        part = rows[i:i + 15]
        if i and rows:
            part = [rows[0]] + part  # repeat the header so the chunk stands alone
        p.chunks.append(Chunk(f"Zeilen {i + 1}-{min(i + 15, len(rows))}", _rows_to_text(part)))
    return p


def _eml(data: bytes) -> Parsed:
    msg = email.message_from_bytes(data, policy=policy.default)
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body else ""
    if body and body.get_content_type() == "text/html":
        text = _strip_html(text)
    head = f"Von: {msg.get('From', '')}\nAn: {msg.get('To', '')}\nDatum: {msg.get('Date', '')}\nBetreff: {msg.get('Subject', '')}"
    return Parsed("eml", _split("E-Mail", head + "\n\n" + text), title=str(msg.get("Subject", "")))


def _strip_html(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|nav|footer|header)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h\d>|</tr>", "\n", h)
    h = re.sub(r"<[^>]+>", " ", h)
    import html
    h = html.unescape(h)
    return re.sub(r"[ \t]+", " ", re.sub(r"\n\s*\n+", "\n\n", h)).strip()


def _html(data: bytes) -> Parsed:
    raw = _decode(data)
    m = re.search(r"(?is)<title[^>]*>(.*?)</title>", raw)
    return Parsed("html", _split("Seite", _strip_html(raw)), title=_strip_html(m.group(1)) if m else "")


def _docx(data: bytes) -> Parsed:
    import docx
    d = docx.Document(io.BytesIO(data))
    p = Parsed("docx")
    para_no, buf = 0, []
    for para in d.paragraphs:
        t = para.text.strip()
        if not t:
            continue
        para_no += 1
        style = (para.style.name or "").lower() if para.style is not None else ""
        if style.startswith("heading") or style == "title":
            if not p.title:
                p.title = t
        buf.append((para_no, t))
    for i in range(0, len(buf), 8):
        part = buf[i:i + 8]
        p.chunks += _split(f"Absatz {part[0][0]}-{part[-1][0]}" if len(part) > 1 else f"Absatz {part[0][0]}", "\n".join(t for _, t in part))
    for ti, tb in enumerate(d.tables, 1):
        rows = [[_cell(c.text) for c in r.cells] for r in tb.rows]
        p.tables.append(Table("", rows, f"Tabelle {ti}"))
        p.chunks += _split(f"Tabelle {ti}", _rows_to_text(rows))
    for rel in d.part.rels.values():
        if "image" in rel.reltype:
            try:
                blob = rel.target_part.blob
                ext = Path(rel.target_part.partname).suffix.lstrip(".").lower() or "png"
                w, h = _dims(blob)
                p.images.append(Image(blob, ext, w, h, "", f"Bild {len(p.images) + 1}"))
            except Exception:
                continue
    return p


def _pptx(data: bytes) -> Parsed:
    from pptx import Presentation
    from pptx.util import Emu  # noqa: F401
    prs = Presentation(io.BytesIO(data))
    p = Parsed("pptx")
    for n, slide in enumerate(prs.slides, 1):
        texts = []
        title = slide.shapes.title.text_frame.text.strip() if slide.shapes.title is not None and slide.shapes.title.has_text_frame else ""
        for sh in slide.shapes:
            if sh.has_text_frame and sh.text_frame.text.strip():
                texts.append(sh.text_frame.text.strip())
            if getattr(sh, "has_table", False) and sh.has_table:
                rows = [[_cell(c.text) for c in r.cells] for r in sh.table.rows]
                p.tables.append(Table(title, rows, f"Folie {n}"))
                texts.append(_rows_to_text(rows))
            if sh.shape_type == 13:  # picture
                try:
                    w, h = _dims(sh.image.blob)
                    p.images.append(Image(sh.image.blob, sh.image.ext, w, h, title, f"Folie {n}"))
                except Exception:
                    pass
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None and slide.notes_slide.notes_text_frame.text.strip():
            texts.append("Notizen: " + slide.notes_slide.notes_text_frame.text.strip())
        p.chunks += _split(f"Folie {n}", "\n".join(dict.fromkeys(texts)))
        if n == 1 and title:
            p.title = title
    return p


def _xlsx(data: bytes) -> Parsed:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    p = Parsed("xlsx")
    for ws in wb.worksheets:
        rows = [[_cell(c) for c in r] for r in ws.iter_rows(values_only=True)]
        while rows and not any(rows[-1]):
            rows.pop()
        if not rows:
            continue
        p.tables.append(Table(ws.title, rows[:60], f"Blatt {ws.title}"))
        header = rows[0]
        step = 20
        for i in range(0, len(rows), step):
            part = rows[i:i + step]
            if i:
                part = [header] + part
            p.chunks.append(Chunk(f"Blatt {ws.title}, Zeilen {i + 1}-{min(i + step, len(rows))}", _rows_to_text(part)))
    return p


def _pdf(data: bytes) -> Parsed:
    from pypdf import PdfReader
    r = PdfReader(io.BytesIO(data))
    p = Parsed("pdf")
    for n, page in enumerate(r.pages, 1):
        try:
            t = page.extract_text() or ""
        except Exception:
            t = ""
        p.chunks += _split(f"S. {n}", t)
        if n == 1 and t.strip():
            p.title = t.strip().splitlines()[0][:100]
    return p


def _dims(blob: bytes) -> tuple[int | None, int | None]:
    try:
        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(blob)) as im:
            return im.size
    except Exception:
        return None, None


def _image(data: bytes) -> Parsed:
    w, h = _dims(data)
    return Parsed("png", images=[Image(data, "png", w, h, "", "Bild")])


def thumbnail_data_url(blob: bytes, max_side: int = 512) -> str | None:
    """Small JPEG preview for the vision model."""
    try:
        import base64
        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(blob)) as im:
            im = im.convert("RGB")
            im.thumbnail((max_side, max_side))
            out = io.BytesIO()
            im.save(out, "JPEG", quality=70)
        return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()
    except Exception:
        return None


# ------------------------------------------------------------------ the committee template
def read_template(data: bytes, name: str = "") -> dict:
    """Structure of a PPT template for the template-analyst: layouts and what each slide holds."""
    from pptx import Presentation
    prs = Presentation(io.BytesIO(data))
    slides = []
    for n, s in enumerate(prs.slides, 1):
        title = s.shapes.title.text_frame.text.strip() if s.shapes.title is not None and s.shapes.title.has_text_frame else ""
        text = [sh.text_frame.text.strip() for sh in s.shapes if sh.has_text_frame and sh.text_frame.text.strip() and sh != s.shapes.title]
        slides.append({"index": n, "title": title or None, "layout": s.slide_layout.name, "text": [t[:200] for t in text][:8],
                       "has_chart": any(getattr(sh, "has_chart", False) and sh.has_chart for sh in s.shapes),
                       "has_image": any(sh.shape_type == 13 for sh in s.shapes)})
    return {"name": name, "slide_count": len(prs.slides), "layouts": [l.name for l in prs.slide_layouts], "slides": slides}
