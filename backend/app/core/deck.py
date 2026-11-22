"""Builds the PowerPoint file. Layout, charts, numbers and sources come from code and the ledger, never from a model."""
from __future__ import annotations

import io
from dataclasses import dataclass, field

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION
from pptx.util import Emu, Pt

VW_BLUE = RGBColor(0x00, 0x1E, 0x50)


@dataclass
class SlideSpec:
    title: str
    bullets: list[str] = field(default_factory=list)
    notes: str = ""
    layout: str | None = None
    chart: dict | None = None  # {type, title, unit, labels, values}
    images: list[tuple[bytes, str]] = field(default_factory=list)  # (data, caption)
    table: list[list[str]] | None = None
    footer: str = ""


def _layout(prs, name: str | None, fallback: int):
    if name:
        for l in prs.slide_layouts:
            if l.name == name:
                return l
    n = len(prs.slide_layouts)
    return prs.slide_layouts[min(fallback, n - 1)]


def _drop_all_slides(prs) -> None:
    ids = prs.slides._sldIdLst
    for sld in list(ids):
        prs.part.drop_rel(sld.rId)
        ids.remove(sld)


def _placeholders(slide):
    title, body = slide.shapes.title, None
    for ph in slide.placeholders:
        t = ph.placeholder_format.type
        if body is None and ph != title and "BODY" in str(t) or "OBJECT" in str(t):
            body = ph
    return title, body


def build_deck(slides: list[SlideSpec], *, template: bytes | None, title: str, subtitle: str, lang: str = "de") -> bytes:
    if template:
        prs = Presentation(io.BytesIO(template))
        _drop_all_slides(prs)
    else:
        prs = Presentation()
        prs.slide_width, prs.slide_height = Emu(12192000), Emu(6858000)  # 16:9
    W, H = prs.slide_width, prs.slide_height

    # title slide
    s = prs.slides.add_slide(_layout(prs, None, 0))
    if s.shapes.title is not None:
        s.shapes.title.text = title
    subs = [p for p in s.placeholders if p.placeholder_format.idx == 1]
    if subs:
        subs[0].text = subtitle

    for spec in slides:
        sl = prs.slides.add_slide(_layout(prs, spec.layout, 1))
        t, body = _placeholders(sl)
        if t is not None:
            t.text = spec.title
            for p in t.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = Pt(26) if len(spec.title) < 90 else Pt(22)
        else:
            tb = sl.shapes.add_textbox(Emu(int(W * .05)), Emu(int(H * .04)), Emu(int(W * .9)), Emu(int(H * .14)))
            tb.text_frame.text = spec.title
            tb.text_frame.paragraphs[0].runs[0].font.size = Pt(26)
            tb.text_frame.paragraphs[0].runs[0].font.bold = True
            tb.text_frame.word_wrap = True
        has_visual = bool(spec.chart or spec.images or spec.table)
        left, top = Emu(int(W * .05)), Emu(int(H * .22))
        text_w = Emu(int(W * (.45 if has_visual else .9)))
        height = Emu(int(H * .62))
        if body is not None:
            body.left, body.top, body.width, body.height = left, top, text_w, height
            tf = body.text_frame
        else:
            tb = sl.shapes.add_textbox(left, top, text_w, height)
            tf = tb.text_frame
        tf.word_wrap = True
        for i, b in enumerate(spec.bullets):
            para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            para.text = b
            para.level = 0
            for r in para.runs:
                r.font.size = Pt(18 if len(spec.bullets) <= 4 else 16)
        # visual on the right
        vx, vy, vw, vh = Emu(int(W * .53)), Emu(int(H * .22)), Emu(int(W * .42)), Emu(int(H * .6))
        if spec.chart:
            c = spec.chart
            cd = CategoryChartData()
            cd.categories = [str(x) for x in c["labels"]]
            cd.add_series(c.get("unit") or c.get("title") or "", [float(v) for v in c["values"]])
            kind = XL_CHART_TYPE.LINE_MARKERS if c.get("type") == "line" else XL_CHART_TYPE.COLUMN_CLUSTERED if c.get("type") == "column" else XL_CHART_TYPE.BAR_CLUSTERED
            gf = sl.shapes.add_chart(kind, vx, vy, vw, vh, cd)
            ch = gf.chart
            ch.has_legend = False
            ch.has_title = bool(c.get("title"))
            if ch.has_title:
                ch.chart_title.text_frame.text = c["title"] + (f" ({c['unit']})" if c.get("unit") else "")
                ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(14)
            plot = ch.plots[0]
            plot.has_data_labels = True
            plot.data_labels.font.size = Pt(12)
            plot.data_labels.number_format = "General"
            plot.data_labels.number_format_is_linked = False
        elif spec.table:
            rows, cols = len(spec.table), max(len(r) for r in spec.table)
            tbl = sl.shapes.add_table(rows, cols, vx, vy, vw, Emu(int(vh * min(1, rows / 8)))).table
            for ri, r in enumerate(spec.table):
                for ci in range(cols):
                    cell = tbl.cell(ri, ci)
                    cell.text = r[ci] if ci < len(r) else ""
                    for p in cell.text_frame.paragraphs:
                        for run in p.runs:
                            run.font.size = Pt(11)
        elif spec.images:
            data, cap = spec.images[0]
            try:
                from PIL import Image
                with Image.open(io.BytesIO(data)) as im:
                    iw, ih = im.size
                scale = min(vw / iw, (vh * .9) / ih)
                pw, ph_ = int(iw * scale), int(ih * scale)
                sl.shapes.add_picture(io.BytesIO(data), vx, vy, Emu(pw), Emu(ph_))
                if cap:
                    cb = sl.shapes.add_textbox(vx, Emu(vy + ph_ + 40000), vw, Emu(300000))
                    cb.text_frame.text = cap
                    cb.text_frame.paragraphs[0].runs[0].font.size = Pt(11)
            except Exception:
                pass
        if spec.footer:
            fb = sl.shapes.add_textbox(Emu(int(W * .05)), Emu(int(H * .92)), Emu(int(W * .9)), Emu(int(H * .06)))
            fb.text_frame.text = spec.footer
            fb.text_frame.word_wrap = True
            fb.text_frame.paragraphs[0].runs[0].font.size = Pt(9)
            fb.text_frame.paragraphs[0].runs[0].font.color.rgb = RGBColor(0x66, 0x66, 0x66)
        if spec.notes:
            sl.notes_slide.notes_text_frame.text = spec.notes
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()
