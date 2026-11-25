"""Figures that sit inside a page: charts, diagrams and photos cut out of a PDF page at their own size, with the caption that belongs to them.

A PDF holds pictures as embedded bitmaps (photos, scanned charts) or as vector drawings (charts made by Excel or PowerPoint). Neither can be copied as
one file, so the page is rendered once and the region around the figure is cropped. Code finds the regions (picture objects, dense clusters of drawing
objects); the asset-analyst may later correct a crop by looking at it.
"""
from __future__ import annotations

import io
import re

from .model import Image, Options

CAPTION_START = re.compile(r"^\s*(abbildung|abb\.?|figure|fig\.?|grafik|chart|diagramm|bild|quelle|source)\b", re.I)


def crop_fraction(blob: bytes, box: tuple[float, float, float, float], max_px: int = 2400) -> tuple[bytes, int, int] | None:
    """The part of a picture inside a box given as fractions (x0, y0, x1, y1), as PNG. None if the box is unusable."""
    try:
        from PIL import Image as PILImage, ImageOps

        with PILImage.open(io.BytesIO(blob)) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
            x0, y0, x1, y1 = box
            l, t, r, b = int(max(0, x0) * w), int(max(0, y0) * h), int(min(1, x1) * w), int(min(1, y1) * h)
            if r - l < 40 or b - t < 40:
                return None
            c = im.crop((l, t, r, b)).convert("RGB")
            c.thumbnail((max_px, max_px))
            out = io.BytesIO()
            c.save(out, "PNG", optimize=True)
            return out.getvalue(), c.width, c.height
    except Exception:  # noqa: BLE001
        return None


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _near(a, b, gap: float) -> bool:
    return not (a[2] + gap < b[0] or b[2] + gap < a[0] or a[3] + gap < b[1] or b[3] + gap < a[1])


def _cluster(boxes: list[tuple], gap: float) -> list[tuple]:
    boxes = list(boxes)
    merged = True
    while merged and len(boxes) > 1:
        merged = False
        out: list[tuple] = []
        while boxes:
            cur = boxes.pop()
            i = 0
            while i < len(boxes):
                if _near(cur, boxes[i], gap):
                    cur = _union(cur, boxes.pop(i))
                    merged = True
                    i = 0
                else:
                    i += 1
            out.append(cur)
        boxes = out
    return boxes


def pdf_figures(doc, page_texts: list[str], opts: Options, *, max_figures: int = 40) -> list[Image]:
    """Figures of a PDF as cropped pictures. `doc` is an open pypdfium2 document."""
    try:
        import pypdfium2.raw as raw
    except Exception:  # noqa: BLE001
        return []
    out: list[Image] = []
    for i in range(min(len(doc), opts.max_pages)):
        if len(out) >= max_figures:
            break
        page = doc[i]
        try:
            w, h = page.get_size()
            area = w * h
            pics, paths = [], []
            for obj in page.get_objects(filter=[raw.FPDF_PAGEOBJ_IMAGE, raw.FPDF_PAGEOBJ_PATH], max_depth=2):
                l, b, r, t = obj.get_bounds()
                box = (l, b, r, t)
                if r - l < 4 and t - b < 4:
                    continue
                if obj.type == raw.FPDF_PAGEOBJ_IMAGE:
                    if (r - l) * (t - b) >= 0.02 * area and (r - l) > 0.12 * w and (t - b) > 0.08 * h:
                        pics.append(box)
                elif (r - l) * (t - b) < 0.6 * area:  # a frame around the whole page is not a figure
                    paths.append(box)
            regions = _cluster(pics, 6.0)
            if len(paths) >= 14:  # a chart is many small bars, lines and ticks close to each other
                for c in _cluster(paths, 10.0):
                    n_in = sum(1 for p in paths if p[0] >= c[0] - 1 and p[2] <= c[2] + 1 and p[1] >= c[1] - 1 and p[3] <= c[3] + 1)
                    if n_in >= 12 and (c[2] - c[0]) > 0.25 * w and (c[3] - c[1]) > 0.12 * h and (c[2] - c[0]) * (c[3] - c[1]) < 0.85 * area:
                        regions.append(c)
            regions = _cluster(regions, 4.0) if len(regions) > 1 else regions
            if not regions:
                continue
            tp = page.get_textpage()
            scale = 2.2 if max(w, h) < 900 else 1.6
            pil = page.render(scale=scale).to_pil().convert("RGB")
            for (l, b, r, t) in sorted(regions, key=lambda x: -x[3])[:3]:
                pad = 8.0
                l, b, r, t = max(0, l - pad), max(0, b - pad), min(w, r + pad), min(h, t + pad)
                below = _text(tp, l, max(0, b - 30), r, b)
                above = _text(tp, l, t, r, min(h, t + 22))
                cap = below if CAPTION_START.match(below) else above if CAPTION_START.match(above) else ""
                cap_text = _first_sentence(cap)
                if cap:  # the caption belongs to the figure: take it along
                    if cap is below:
                        b = max(0, b - 26)
                    else:
                        t = min(h, t + 20)
                px = (int(l * scale), int((h - t) * scale), int(r * scale), int((h - b) * scale))
                crop = pil.crop(px)
                if crop.width < 260 or crop.height < 160:
                    continue
                buf = io.BytesIO()
                crop.save(buf, "PNG", optimize=True)
                out.append(Image(buf.getvalue(), "png", crop.width, crop.height, cap_text, f"S. {i + 1}", context=(page_texts[i] if i < len(page_texts) else "")[:500]))
            tp.close()
        except Exception:  # noqa: BLE001  one page must not stop the file
            continue
        finally:
            page.close()
    return out


def _first_sentence(text: str) -> str:
    """A caption is the first sentence of what stands next to the figure (the text band may also reach the next paragraph)."""
    t = " ".join(text.split())
    m = re.search(r"(?<=[a-zäöü0-9\)])\.\s+(?=[A-ZÄÖÜ])", t[25:])
    return (t[: 25 + m.start() + 1] if m else t)[:160]


def _text(tp, l: float, b: float, r: float, t: float) -> str:
    try:
        return " ".join(tp.get_text_bounded(left=l, bottom=b, right=r, top=t).split())
    except Exception:  # noqa: BLE001
        return ""
