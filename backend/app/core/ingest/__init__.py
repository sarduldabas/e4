"""Reading files: one entry point, `parse_bytes`, for every kind of file a user may drop into the tool.

Code reads everything it can read exactly (text layers, tables, formulas, mail parts, archive members). What code cannot read
(scans, charts and photos) comes back as `Parsed.vision` tasks for the vision model; `apply_vision` puts the transcription back.
"""
from __future__ import annotations

from pathlib import Path

from . import media, office, pdf
from .mail import read_eml, read_msg
from .media import dims, jpeg_of
from .model import Chunk, Image, Options, Parsed, Table, VisionTask
from .text import CHUNK_CHARS, clean, garbled_ratio, split

TEXT_KINDS = {"txt", "md", "csv", "json", "xml", "html", "htm", "log", "tsv"}
IMAGE_KINDS = {"png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff"}
OFFICE_KINDS = {"docx", "pptx", "xlsx"}
SUPPORTED = TEXT_KINDS | IMAGE_KINDS | OFFICE_KINDS | set(office.LEGACY) | {"pdf", "eml", "msg", "zip"}

MAGIC = [(b"%PDF", "pdf"), (b"\x89PNG", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF8", "gif"), (b"BM", "bmp"), (b"II*\x00", "tiff"), (b"MM\x00*", "tiff"),
         (b"\xd0\xcf\x11\xe0", "ole"), (b"PK\x03\x04", "zip"), (b"{\\rtf", "rtf")]


def kind_of(name: str) -> str:
    return Path(name).suffix.lower().lstrip(".")


def sniff(name: str, data: bytes) -> str:
    """The real type: the extension decides unless the content says otherwise (a PDF named .doc, an Office file named .zip)."""
    ext = kind_of(name)
    head = data[:8]
    for magic, kind in MAGIC:
        if head.startswith(magic):
            if kind == "zip":
                import io
                import zipfile

                try:
                    names = zipfile.ZipFile(io.BytesIO(data)).namelist()
                except zipfile.BadZipFile:
                    return ext
                for marker, k in (("word/document.xml", "docx"), ("ppt/presentation.xml", "pptx"), ("xl/workbook.xml", "xlsx")):
                    if marker in names:
                        return k
                if "content.xml" in names and ext in ("odt", "ods", "odp"):
                    return ext
                return "zip"
            if kind == "ole":  # old Office files and Outlook .msg share one container format
                return ext if ext in ("doc", "xls", "ppt", "msg", "dot") else "msg" if b"__substg1.0_" in data[:200000] else ext
            if kind in ("png", "jpg", "gif", "bmp", "tiff") and ext in IMAGE_KINDS:
                return ext
            return kind
    return ext


def parse_bytes(name: str, data: bytes, opts: Options | None = None, _depth: int = 0) -> Parsed:
    opts = opts or Options()
    kind = sniff(name, data)
    if kind not in SUPPORTED:
        raise ValueError(f"file type .{kind or '?'} is not supported")
    if not data:
        raise ValueError("the file is empty")

    def member(n: str, b: bytes, depth: int) -> Parsed:
        return parse_bytes(n, b, opts, depth)

    if kind in office.LEGACY:
        data, target = office.convert_legacy(data, kind)
        p = parse_bytes(f"{Path(name).stem}.{target}", data, opts, _depth)
        p.warnings.append(f"converted from .{kind}")
        p.kind = kind
        return _finish(p, name, kind)
    if kind == "pdf":
        p = pdf.read_pdf(data, opts)
    elif kind == "docx":
        p = office.read_docx(data, opts)
    elif kind == "pptx":
        p = office.read_pptx(data, opts)
    elif kind == "xlsx":
        p = office.read_xlsx(data, opts)
    elif kind == "eml":
        p = read_eml(data, member, opts, _depth)
    elif kind == "msg":
        p = read_msg(data, member, opts, _depth)
    elif kind == "zip":
        p = media.read_zip(data, member, opts, _depth)
    elif kind in IMAGE_KINDS:
        p = media.read_image(data, opts, name)
    elif kind in ("csv", "tsv"):
        p = media.read_csv(data)
    elif kind in ("html", "htm"):
        p = media.read_html(data)
    elif kind == "xml":
        p = media.read_xml(data)
    else:
        p = media.read_text(data, kind)
    return _finish(p, name, kind)


def _finish(p: Parsed, name: str, kind: str) -> Parsed:
    p.kind = kind
    p.title = clean(p.title)[:200] or Path(name).stem
    p.stats.setdefault("chars", sum(len(c.text) for c in p.chunks))
    return p


# ------------------------------------------------------------------------------------------- vision results
def apply_vision(p: Parsed, results: dict[str, dict]) -> int:
    """Put the vision model's transcriptions into the document. `results[key]` = {"text": ..., "tables": [rows...], "description": ...}.

    A scanned or garbled page's text replaces what the text layer gave; a picture or figure adds a chunk. Returns the number applied.
    """
    applied = 0
    by_key = {v.key: v for v in p.vision}
    for key, res in results.items():
        task = by_key.get(key)
        if task is None:
            continue
        text = clean(res.get("text", ""))
        desc = clean(res.get("description", ""))
        tables = res.get("tables") or []
        body = text
        for ti, rows in enumerate(tables, 1):
            rows = [[str(c) for c in r] for r in rows if r]
            if len(rows) >= 2:
                p.tables.append(Table("", rows, f"{task.locator}, Tabelle {ti}"))
                if not any(" | ".join(rows[1][:2]) in body for _ in [0]):
                    body += "\n" + "\n".join(" | ".join(c for c in r if c) for r in rows)
        if desc and task.reason in ("figure", "image"):
            body = (body + "\n" if body else "") + f"Abbildung: {desc}"
        if not body.strip():
            continue
        if task.reason in ("scanned", "garbled"):
            p.chunks = [c for c in p.chunks if c.ref != key]
            new = split(task.locator, body, ref=None)
            at = _insert_at(p, task.locator)
        else:
            new = split(f"{task.locator} (Abbildung)" if task.reason == "figure" else task.locator, body, ref=None)
            at = len(p.chunks)
        for c in new:
            c.flags = ("vision",)
        p.chunks[at:at] = new
        applied += 1
    return applied


def _insert_at(p: Parsed, locator: str) -> int:
    """Keep page order: put a transcribed page where its neighbours are."""
    m = None
    import re

    m = re.match(r"S\. (\d+)", locator)
    if not m:
        return len(p.chunks)
    page = int(m.group(1))
    for i, c in enumerate(p.chunks):
        cm = re.match(r"S\. (\d+)", c.locator)
        if cm and int(cm.group(1)) > page:
            return i
    return len(p.chunks)


# ------------------------------------------------------------------------------------------- previews and templates
def thumbnail_data_url(blob: bytes, max_side: int = 512) -> str | None:
    """Small JPEG preview for the vision model."""
    import base64

    j = jpeg_of(blob, max_side)
    return "data:image/jpeg;base64," + base64.b64encode(j[0]).decode() if j else None


def read_template(data: bytes, name: str = "") -> dict:
    """Structure of a PPT template for the template-analyst: layouts, placeholders, and what each slide holds."""
    import io

    from pptx import Presentation

    prs = Presentation(io.BytesIO(data))
    slides = []
    for n, s in enumerate(prs.slides, 1):
        title = s.shapes.title.text_frame.text.strip() if s.shapes.title is not None and s.shapes.title.has_text_frame else ""
        text = [sh.text_frame.text.strip() for sh in s.shapes if getattr(sh, "has_text_frame", False) and sh.has_text_frame and sh.text_frame.text.strip() and sh != s.shapes.title]
        tables = [sh for sh in s.shapes if getattr(sh, "has_table", False) and sh.has_table]
        slides.append({"index": n, "title": title or None, "layout": s.slide_layout.name, "text": [t[:240] for t in text][:10],
                       "has_chart": any(getattr(sh, "has_chart", False) and sh.has_chart for sh in s.shapes),
                       "has_image": any(sh.shape_type == 13 for sh in s.shapes), "has_table": bool(tables),
                       "notes": (s.notes_slide.notes_text_frame.text.strip()[:240] if s.has_notes_slide and s.notes_slide.notes_text_frame is not None else "")})
    layouts = []
    for l in prs.slide_layouts:
        phs = [{"type": str(ph.placeholder_format.type).split(".")[-1].split(" ")[0], "name": ph.name} for ph in l.placeholders]
        layouts.append({"name": l.name, "placeholders": phs})
    return {"name": name, "slide_count": len(prs.slides), "layouts": [l["name"] for l in layouts], "layout_details": layouts[:30], "slides": slides,
            "size_in": [round(prs.slide_width / 914400, 2), round(prs.slide_height / 914400, 2)]}
