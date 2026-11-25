"""PDF: text layer, tables, and what the text layer cannot give (scans, garbled text, figures) as vision tasks."""
from __future__ import annotations

import io
import time

from .figures import pdf_figures
from .model import Chunk, Image, Options, Parsed, Table, VisionTask
from .text import clean, cell, drop_repeated_lines, garbled_ratio, rows_to_text, split


def _jpeg(pil, max_px: int) -> bytes:
    pil = pil.convert("RGB")
    pil.thumbnail((max_px, max_px))
    out = io.BytesIO()
    pil.save(out, "JPEG", quality=78)
    return out.getvalue()


def _image_coverage(page) -> float:
    """Share of the page area covered by pictures (0..1). Charts and scans are usually one big picture."""
    try:
        import pypdfium2.raw as raw

        w, h = page.get_size()
        area = 0.0
        for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE], max_depth=2):
            l, b, r, t = obj.get_bounds()
            area += max(0.0, r - l) * max(0.0, t - b)
        return min(1.0, area / (w * h)) if w and h else 0.0
    except Exception:  # noqa: BLE001
        return 0.0


def read_pdf(data: bytes, opts: Options | None = None) -> Parsed:
    import pypdfium2 as pdfium

    opts = opts or Options()
    try:
        doc = pdfium.PdfDocument(data)
    except pdfium.PdfiumError as e:
        if "password" in str(e).lower():
            raise ValueError("the PDF is password protected") from e
        raise ValueError(f"the PDF cannot be opened ({e})") from e
    n_pages = len(doc)
    p = Parsed("pdf", stats={"pages": n_pages})
    meta = {}
    try:
        meta = {k.lower(): v for k, v in doc.get_metadata_dict().items() if v}
    except Exception:  # noqa: BLE001
        pass
    p.meta = {k: meta[k] for k in ("title", "author", "creationdate", "moddate", "subject") if k in meta}
    pages: list[str] = []
    flags: list[tuple[str, float]] = []  # per page: (reason or "", image coverage)
    for i in range(min(n_pages, opts.max_pages)):
        page = doc[i]
        try:
            tp = page.get_textpage()
            t = clean(tp.get_text_range())
            tp.close()
        except Exception:  # noqa: BLE001
            t = ""
        cov = _image_coverage(page)
        reason = ""
        if len(t) < 25:
            reason = "scanned"
        elif garbled_ratio(t) > 0.3:
            reason = "garbled"
        elif cov > 0.35 and len(t) < 1500:
            reason = "figure"
        pages.append(t)
        flags.append((reason, cov))
        page.close()
    if n_pages > opts.max_pages:
        p.warnings.append(f"only the first {opts.max_pages} of {n_pages} pages were read")
    pages = drop_repeated_lines(pages)

    # vision budget: pages without usable text first, then figures; in page order inside each group
    need = [i for i, (r, _) in enumerate(flags) if r in ("scanned", "garbled")]
    figs = [i for i, (r, _) in enumerate(flags) if r == "figure"]
    chosen = sorted((need + figs)[: opts.max_vision_pages])
    skipped_need = [i + 1 for i in need if i not in set(chosen)]
    if skipped_need:
        p.warnings.append(f"pages without readable text were not sent to the vision model (limit {opts.max_vision_pages}): {_ranges(skipped_need)}")
    keys: dict[int, str] = {}
    page_images: dict[int, tuple | None] = {}
    for i in chosen:
        page = doc[i]
        try:
            scale = opts.max_image_px / max(page.get_size())
            pil = page.render(scale=max(0.5, min(scale, 3.0))).to_pil()
            jpg = _jpeg(pil, opts.max_image_px)
        except Exception as e:  # noqa: BLE001
            p.warnings.append(f"S. {i + 1}: could not be rendered ({e.__class__.__name__})")
            continue
        finally:
            page.close()
        reason = flags[i][0]
        key = f"p{i + 1}"
        keys[i] = key
        p.vision.append(VisionTask(key, f"S. {i + 1}", jpg, reason, hint=meta.get("title", ""), existing_text=pages[i][:1500]))
        page_images[i] = (jpg, pil.width, pil.height) if reason == "figure" and len(jpg) > 20_000 else None

    for i, t in enumerate(pages):
        reason = flags[i][0]
        key = keys.get(i)
        if reason == "scanned" and key is None and not t:
            continue
        if reason == "garbled" and key:
            continue  # the vision result replaces the broken text layer
        if t:
            p.chunks += split(f"S. {i + 1}", t, ref=key if reason == "garbled" else None)
    unread = [i + 1 for i, (r, _) in enumerate(flags) if r == "scanned" and i not in keys]
    p.stats.update(scanned_pages=len([1 for r, _ in flags if r == "scanned"]), garbled_pages=len([1 for r, _ in flags if r == "garbled"]),
                   figure_pages=len(figs), vision_pages=len(keys), chars=sum(len(t) for t in pages))
    if unread:
        p.warnings.append(f"no text on pages {_ranges(unread)} (scanned) and no vision model was used")

    try:  # the figures themselves, cut out of their pages; a figure page without a found figure keeps its whole-page picture
        figs = pdf_figures(doc, pages, opts)
    except Exception as e:  # noqa: BLE001
        figs = []
        p.warnings.append(f"figures could not be cut out ({e.__class__.__name__})")
    p.images += figs
    have = {im.locator for im in figs}
    for i, v in page_images.items():
        if v and f"S. {i + 1}" not in have:
            p.images.append(Image(v[0], "jpg", v[1], v[2], "", f"S. {i + 1}"))
    p.stats["figures"] = len(p.images)
    _tables(data, pages, p, opts)
    first = next((t for t in pages if t), "")
    p.title = str(meta.get("title") or (first.splitlines()[0][:100] if first else ""))
    return p


def _ranges(nums: list[int]) -> str:
    out, start, prev = [], None, None
    for n in nums:
        if start is None:
            start = prev = n
        elif n == prev + 1:
            prev = n
        else:
            out.append(f"{start}-{prev}" if prev != start else str(start))
            start = prev = n
    if start is not None:
        out.append(f"{start}-{prev}" if prev != start else str(start))
    return ", ".join(out[:12]) + (" …" if len(out) > 12 else "")


def _tables(data: bytes, pages: list[str], p: Parsed, opts: Options) -> None:
    """Tables with ruling lines, as rows. Time-boxed: huge reports are not stalled by table detection."""
    try:
        import pdfplumber
    except ImportError:
        return
    started = time.monotonic()
    done_pages = 0
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            for i, page in enumerate(pdf.pages[: len(pages)]):
                if time.monotonic() - started > opts.table_seconds:
                    p.warnings.append(f"table detection stopped after {done_pages} pages (time limit)")
                    break
                if len(pages[i]) < 80 or len(p.tables) >= 60:
                    continue
                done_pages += 1
                try:
                    found = page.find_tables()
                except Exception:  # noqa: BLE001
                    continue
                for tb in found:
                    rows = [[cell(c) for c in r] for r in (tb.extract() or [])]
                    rows = [r for r in rows if any(r)]
                    if len(rows) >= 2 and max(len(r) for r in rows) >= 2:
                        p.tables.append(Table("", rows[:80], f"Tabelle S. {i + 1}"))
                        p.chunks += split(f"Tabelle S. {i + 1}", rows_to_text(rows))
                page.flush_cache()
    except Exception as e:  # noqa: BLE001
        p.warnings.append(f"tables could not be read ({e.__class__.__name__})")
