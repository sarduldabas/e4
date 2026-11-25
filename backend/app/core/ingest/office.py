"""Word, PowerPoint, Excel. Legacy formats are converted with LibreOffice when it is installed."""
from __future__ import annotations

import datetime as dt
import io
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .media import add_picture
from .model import Chunk, Options, Parsed, Table
from .text import cell, clean, rows_to_text, split


# ------------------------------------------------------------------------------------------- legacy
LEGACY = {"doc": "docx", "xls": "xlsx", "ppt": "pptx", "rtf": "docx", "odt": "docx", "ods": "xlsx", "odp": "pptx", "dot": "docx", "xlsm": "xlsx"}


def convert_legacy(data: bytes, ext: str) -> tuple[bytes, str]:
    """Old binary formats cannot be read reliably in plain Python; LibreOffice converts them. Without it the user is asked to re-save."""
    target = LEGACY[ext]
    exe = shutil.which("soffice") or shutil.which("libreoffice")
    if not exe:
        raise ValueError(f".{ext} files need LibreOffice to be read here; please save the file as .{target} and upload it again")
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / f"in.{ext}"
        src.write_bytes(data)
        try:
            subprocess.run([exe, "--headless", "--convert-to", target, "--outdir", d, str(src)], check=True, capture_output=True, timeout=180,
                           env={"HOME": d, "PATH": "/usr/bin:/bin:/usr/local/bin"} if exe.startswith("/") else None)
        except (subprocess.SubprocessError, OSError) as e:
            raise ValueError(f"the .{ext} file could not be converted ({e.__class__.__name__}); please save it as .{target}") from e
        out = Path(d) / f"in.{target}"
        if not out.exists():
            raise ValueError(f"the .{ext} file could not be converted; please save it as .{target}")
        return out.read_bytes(), target


# ------------------------------------------------------------------------------------------- docx
def _core(props) -> dict:
    out = {}
    for k in ("author", "title", "subject", "created", "modified", "last_modified_by"):
        v = getattr(props, k, None)
        if v:
            out[k] = v.date().isoformat() if isinstance(v, (dt.datetime, dt.date)) else str(v)
    return out


def _dedupe(cells: list[str]) -> list[str]:
    out = []
    for c in cells:
        if not out or c != out[-1] or not c:
            out.append(c)
    return out


def read_docx(data: bytes, opts: Options | None = None) -> Parsed:
    import docx
    from docx.table import Table as DTable
    from docx.text.paragraph import Paragraph

    opts = opts or Options()
    d = docx.Document(io.BytesIO(data))
    p = Parsed("docx", meta=_core(d.core_properties))
    heading, buf, para_no, tbl_no = "", [], 0, 0

    def flush():
        nonlocal buf
        if buf:
            first, last = buf[0][0], buf[-1][0]
            loc = f"„{heading}“" if heading else (f"Absatz {first}-{last}" if first != last else f"Absatz {first}")
            if heading:
                loc += f", Abs. {first}-{last}" if first != last else f", Abs. {first}"
            p.chunks += split(loc, "\n".join(t for _, t in buf))
        buf = []

    for child in d.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, d)
            t = para.text.strip()
            if not t:
                continue
            style = (para.style.name or "").lower() if para.style is not None else ""
            if style.startswith("heading") or style in ("title", "überschrift") or style.startswith("überschrift"):
                flush()
                heading = t[:120]
                if not p.title and (style == "title" or style.endswith("1")):
                    p.title = t
                continue
            para_no += 1
            bullet = "• " if "list" in style or "aufzähl" in style else ""
            buf.append((para_no, bullet + t))
            if sum(len(x) for _, x in buf) > 6000:
                flush()
        elif tag == "tbl":
            flush()
            tbl_no += 1
            tb = DTable(child, d)
            rows = [_dedupe([cell(c.text) for c in r.cells]) for r in tb.rows]
            rows = [r for r in rows if any(r)]
            if rows:
                p.tables.append(Table(heading, rows, f"Tabelle {tbl_no}"))
                p.chunks += split(f"Tabelle {tbl_no}" + (f" („{heading}“)" if heading else ""), rows_to_text(rows))
    flush()
    try:  # reviewer comments often hold the decisions
        comments = [f"{c.author or ''}: {c.text}".strip() for c in d.comments]
        if comments:
            p.chunks += split("Kommentare", "\n".join(comments))
    except Exception:  # noqa: BLE001
        pass
    try:
        sec = d.sections[0]
        head = " ".join(x.text.strip() for x in list(sec.header.paragraphs) + list(sec.footer.paragraphs) if x.text.strip())
        if head:
            p.meta["header_footer"] = head[:300]
    except Exception:  # noqa: BLE001
        pass
    n = 0
    for rel in d.part.rels.values():
        if "image" in rel.reltype:
            try:
                n += 1
                add_picture(p, rel.target_part.blob, Path(str(rel.target_part.partname)).suffix.lstrip(".").lower(), f"Bild {n}", "", opts)
            except Exception:  # noqa: BLE001
                continue
    p.title = p.title or p.meta.get("title", "")
    p.stats.update(paragraphs=para_no, tables=tbl_no, chars=sum(len(c.text) for c in p.chunks))
    return p


# ------------------------------------------------------------------------------------------- pptx
def _shapes(shapes):
    for sh in shapes:
        if sh.shape_type == 6 and hasattr(sh, "shapes"):  # group
            yield from _shapes(sh.shapes)
        else:
            yield sh


def _chart_text(ch) -> str:
    try:
        title = ch.chart_title.text_frame.text.strip() if ch.has_title and ch.chart_title.has_text_frame else ""
        plot = ch.plots[0]
        cats = [str(c) for c in plot.categories]
        lines = [f"Diagramm{(' „' + title + '“') if title else ''} ({str(ch.chart_type).split('.')[-1].split(' ')[0].lower()})"]
        if cats:
            lines.append("Kategorien: " + " | ".join(cats))
        for s in plot.series:
            vals = [cell(v) for v in s.values]
            lines.append(f"{s.name}: " + " | ".join(vals))
        return "\n".join(lines)
    except Exception:  # noqa: BLE001
        return ""


def read_pptx(data: bytes, opts: Options | None = None) -> Parsed:
    from pptx import Presentation

    opts = opts or Options()
    prs = Presentation(io.BytesIO(data))
    p = Parsed("pptx", meta=_core(prs.core_properties))
    for n, slide in enumerate(prs.slides, 1):
        title = ""
        try:
            if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
                title = slide.shapes.title.text_frame.text.strip()
        except Exception:  # noqa: BLE001
            pass
        items = []
        pics = 0
        for sh in sorted(_shapes(slide.shapes), key=lambda s: (s.top or 0, s.left or 0)):
            if getattr(sh, "has_text_frame", False) and sh.has_text_frame:
                t = sh.text_frame.text.strip()
                if t and t != title:
                    items.append(t)
            if getattr(sh, "has_table", False) and sh.has_table:
                rows = [[cell(c.text) for c in r.cells] for r in sh.table.rows]
                p.tables.append(Table(title, rows, f"Folie {n}"))
                items.append(rows_to_text(rows))
            if getattr(sh, "has_chart", False) and sh.has_chart:
                ct = _chart_text(sh.chart)
                if ct:
                    items.append(ct)
            if sh.shape_type == 13:
                try:
                    pics += 1
                    add_picture(p, sh.image.blob, sh.image.ext, f"Folie {n}", title, opts, hint=f"Folie {n}: {title}")
                except Exception:  # noqa: BLE001
                    pass
        notes = ""
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            notes = slide.notes_slide.notes_text_frame.text.strip()
        body = ("Titel: " + title + "\n" if title else "") + "\n".join(dict.fromkeys(items))
        hidden = slide._element.get("show") == "0"
        loc = f"Folie {n}" + (f" („{title[:60]}“)" if title else "") + (" – ausgeblendet" if hidden else "")
        p.chunks += split(loc, body)
        if notes:
            p.chunks += split(f"Folie {n}, Notizen", notes)
        if n == 1 and title:
            p.title = title
    p.stats.update(slides=len(prs.slides))
    return p


# ------------------------------------------------------------------------------------------- xlsx
def _xl(v) -> str:
    if isinstance(v, dt.datetime):
        return v.date().isoformat() if not (v.hour or v.minute or v.second) else v.isoformat(sep=" ", timespec="minutes")
    if isinstance(v, dt.date):
        return v.isoformat()
    return cell(v)


def read_xlsx(data: bytes, opts: Options | None = None) -> Parsed:
    import openpyxl

    opts = opts or Options()
    wb = openpyxl.load_workbook(io.BytesIO(data), data_only=True, read_only=True)
    p = Parsed("xlsx")
    try:
        p.meta = _core(wb.properties)
    except Exception:  # noqa: BLE001
        pass
    total_rows = 0
    sheet_rows: dict[str, list[list[str]]] = {}
    for ws in wb.worksheets:
        hidden = getattr(ws, "sheet_state", "visible") != "visible"
        rows: list[list[str]] = []
        for r in ws.iter_rows(values_only=True):
            row = [_xl(c) for c in r]
            if any(row):
                rows.append(row)
            if total_rows + len(rows) >= opts.max_rows:
                p.warnings.append(f"Blatt „{ws.title}“: only the first {len(rows)} rows were read (limit {opts.max_rows} rows per workbook)")
                break
        total_rows += len(rows)
        while rows and not any(rows[-1]):
            rows.pop()
        if not rows:
            continue
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        keep = [j for j in range(width) if any(r[j] for r in rows)]  # drop empty columns
        rows = [[r[j] for j in keep] for r in rows]
        sheet_rows[ws.title] = rows
        name = ws.title + (" (ausgeblendet)" if hidden else "")
        p.tables.append(Table(ws.title, rows[:60], f"Blatt {ws.title}"))
        header, cur, start, size = rows[0], [], 1, 0
        for i, r in enumerate(rows[1:], 2):
            line = " | ".join(c for c in r if c)
            if cur and size + len(line) > 1800:
                p.chunks.append(Chunk(f"Blatt „{name}“, Z. {start}-{i - 1}", rows_to_text([header] + cur)))
                cur, size, start = [], 0, i
            cur.append(r)
            size += len(line) + 1
        if cur or len(rows) == 1:
            p.chunks.append(Chunk(f"Blatt „{name}“, Z. {start}-{len(rows)}", rows_to_text([header] + cur)))
        if len(rows) > 150:  # a big table: the column statistics are what an analyst needs first
            stat = _column_stats(rows)
            if stat:
                p.chunks.append(Chunk(f"Blatt „{name}“, Spaltenstatistik", stat))
    wb.close()
    # formulas explain how a figure was derived; they need a full (not streaming) load, so only for files of moderate size
    if len(data) < 6_000_000:
        try:
            wf = openpyxl.load_workbook(io.BytesIO(data), data_only=False)
            for ws in wf.worksheets:
                fs = []
                for row in ws.iter_rows():
                    for c in row:
                        if isinstance(c.value, str) and c.value.startswith("=") and len(fs) < 150:
                            fs.append(f"{c.coordinate}: {c.value}")
                if fs:
                    p.chunks += split(f"Blatt „{ws.title}“, Formeln", "\n".join(fs))
        except Exception:  # noqa: BLE001
            pass
    p.stats.update(sheets=len(sheet_rows), rows=total_rows)
    return p


def _num(v: str) -> float | None:
    """A number in German (1.234,5) or English (1,234.5) notation, with optional % or currency; None for anything else."""
    t = re.sub(r"[\s€$%]|EUR|USD", "", v)
    if not re.fullmatch(r"-?[\d.,]+", t) or not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".") if len(t.rsplit(",", 1)[1]) != 3 or t.count(",") > 1 and False else t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def _column_stats(rows: list[list[str]]) -> str:
    head, body = rows[0], rows[1:]
    out = []
    for j, h in enumerate(head):
        vals = [r[j] for r in body if j < len(r) and r[j]]
        nums = [x for x in (_num(v) for v in vals) if x is not None]
        if vals and len(nums) >= 0.8 * len(vals):
            out.append(f"{h or f'Spalte {j + 1}'}: {len(nums)} Werte, Summe {sum(nums):.10g}, Mittel {sum(nums) / len(nums):.10g}, min {min(nums):.10g}, max {max(nums):.10g}")
        elif vals:
            distinct = sorted(set(vals))
            out.append(f"{h or f'Spalte {j + 1}'}: {len(vals)} Einträge, {len(distinct)} verschiedene" + (f": {', '.join(distinct[:12])}" if len(distinct) <= 12 else ""))
    return "\n".join(out)
