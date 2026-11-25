"""Draws slide specs into a PowerPoint file. Everything on a slide comes from the spec: no text, number or colour is decided here."""
from __future__ import annotations

import io

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Pt

from . import fit
from .spec import layouts
from .theme import theme_of

NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}
TONES = {"decision": "primary", "info": "accent", "warn": "warn", "good": "good"}


def _rgb(h: str) -> RGBColor:
    return RGBColor.from_string(h.lstrip("#").upper())


class Canvas:
    def __init__(self, prs):
        self.W, self.H = prs.slide_width, prs.slide_height
        self.sx, self.sy = self.W / 1280, self.H / 720

    def box(self, b: dict) -> tuple[Emu, Emu, Emu, Emu]:
        return Emu(int(b["x"] * self.sx)), Emu(int(b["y"] * self.sy)), Emu(int(b["w"] * self.sx)), Emu(int(b["h"] * self.sy))

    def pt(self, size: float) -> Pt:
        return Pt(size * self.sy / 9525 * 0.75)  # canvas px -> points (on the default 13.333 in wide slide 1 px = 0.75 pt)


def _frame(shape, *, margin=0.0, anchor=MSO_ANCHOR.TOP):
    tf = shape.text_frame
    tf.word_wrap = True
    tf.auto_size = None
    tf.vertical_anchor = anchor
    m = Emu(int(margin))
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = m
    return tf


def _run(par, text, *, size, color, bold=False, font=None, cv=None):
    r = par.add_run()
    r.text = text
    r.font.size = cv.pt(size)
    r.font.bold = bold
    r.font.color.rgb = _rgb(color)
    if font:
        r.font.name = font
    return r


def _rect(sl, x, y, w, h, fill, *, line=None, shape=MSO_SHAPE.RECTANGLE):
    sp = sl.shapes.add_shape(shape, x, y, w, h)
    sp.shadow.inherit = False
    st = sp._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}style")
    if st is not None:
        sp._element.remove(st)  # the theme's shape style would add a shadow and a line
    if fill:
        sp.fill.solid()
        sp.fill.fore_color.rgb = _rgb(fill)
    else:
        sp.fill.background()
    if line:
        sp.line.color.rgb = _rgb(line)
        sp.line.width = Pt(0.75)
    else:
        sp.line.fill.background()
    return sp


def _bullet(par, level: int, size_px: float, cv: Canvas):
    pPr = par._p.get_or_add_pPr()
    indent = int(size_px * 1.1 * cv.sx)
    pPr.set("marL", str(indent * (1 + level)))
    pPr.set("indent", str(-indent))
    for tag in ("buNone", "buChar", "buAutoNum"):
        for el in pPr.findall(f"a:{tag}", NS):
            pPr.remove(el)
    bu = etree.SubElement(pPr, f"{{{NS['a']}}}buChar")
    bu.set("char", "–" if level else "•")


class Deck:
    def __init__(self, template: bytes | None, lang: str):
        self.lang = lang
        self.theme = theme_of(template)
        self.template = bool(template)
        if template:
            self.prs = Presentation(io.BytesIO(template))
            ids = self.prs.slides._sldIdLst
            for sld in list(ids):
                self.prs.part.drop_rel(sld.rId)
                ids.remove(sld)
        else:
            self.prs = Presentation()
            self.prs.slide_width, self.prs.slide_height = Emu(12192000), Emu(6858000)
        self.cv = Canvas(self.prs)
        self.c = self.theme["colors"]
        self.L = layouts()
        self.font_h = None if self.template else self.theme["fonts"]["heading"]
        self.font_b = None if self.template else self.theme["fonts"]["body"]
        self.n = 0

    # ------------------------------------------------------------ layouts of the template
    def _layout(self, kind: str):
        ls = list(self.prs.slide_layouts)
        if not self.template:
            return ls[6] if len(ls) > 6 else ls[-1]  # blank
        def has(l, t):
            return any(str(p.placeholder_format.type).startswith(t) for p in l.placeholders)
        if kind == "title":
            for l in ls:
                if has(l, "CENTER_TITLE") or (has(l, "TITLE") and has(l, "SUBTITLE")):
                    return l
            return ls[0]
        for l in ls:  # a layout with a title and nothing else
            if has(l, "TITLE") and len(l.placeholders) <= 4 and not has(l, "BODY") and not has(l, "SUBTITLE") and not has(l, "OBJECT"):
                return l
        for l in ls:
            if has(l, "TITLE") and not has(l, "SUBTITLE"):
                return l
        return ls[-1]

    def _clear_placeholders(self, sl, keep):
        for ph in list(sl.placeholders):
            if ph not in keep:
                ph._element.getparent().remove(ph._element)

    # ------------------------------------------------------------ slides
    def title_slide(self, spec: dict) -> None:
        sl = self.prs.slides.add_slide(self._layout("title"))
        cv, c = self.cv, self.c
        if self.template:
            t = sl.shapes.title
            if t is not None:
                t.text = spec["title"]
            subs = [p for p in sl.placeholders if p.placeholder_format.idx == 1]
            if subs:
                subs[0].text = spec.get("subtitle", "")
            self._clear_placeholders(sl, [p for p in [t] + subs if p is not None])
        else:
            _rect(sl, 0, 0, cv.W, cv.H, c["primary"])
            _rect(sl, Emu(int(56 * cv.sx)), Emu(int(250 * cv.sy)), Emu(int(8 * cv.sx)), Emu(int(190 * cv.sy)), c["accent"])
            tb = sl.shapes.add_textbox(Emu(int(88 * cv.sx)), Emu(int(240 * cv.sy)), Emu(int(1100 * cv.sx)), Emu(int(130 * cv.sy)))
            tf = _frame(tb, anchor=MSO_ANCHOR.TOP)
            _run(tf.paragraphs[0], spec["title"], size=spec.get("title_size", 40) + 10, color=c["on_primary"], bold=True, font=self.font_h, cv=cv)
            sb = sl.shapes.add_textbox(Emu(int(88 * cv.sx)), Emu(int(392 * cv.sy)), Emu(int(1100 * cv.sx)), Emu(int(60 * cv.sy)))
            _run(_frame(sb).paragraphs[0], spec.get("subtitle", ""), size=22, color="#C9D6E6", font=self.font_b, cv=cv)
        self._notes(sl, spec)
        self.n += 1

    def slide(self, spec: dict) -> None:
        if spec.get("kind") == "title":
            return self.title_slide(spec)
        cv, c, L = self.cv, self.c, self.L
        sl = self.prs.slides.add_slide(self._layout("content"))
        tx, ty, tw, th = cv.box(L["title_box"])
        t = sl.shapes.title
        if t is not None and self.template:
            if t.top is None or t.top + (t.height or 0) > int(140 * cv.sy):
                t.left, t.top, t.width, t.height = tx, ty, tw, th
            t.text = spec["title"]
            for p in t.text_frame.paragraphs:
                for r in p.runs:
                    r.font.size = cv.pt(spec["title_size"])
            self._clear_placeholders(sl, [t])
        else:
            if t is not None:
                self._clear_placeholders(sl, [])
            _rect(sl, Emu(int(56 * cv.sx)), Emu(int(40 * cv.sy)), Emu(int(6 * cv.sx)), Emu(int(70 * cv.sy)), c["accent"])
            tb = sl.shapes.add_textbox(Emu(int(76 * cv.sx)), ty, Emu(int(1148 * cv.sx)), th)
            tf = _frame(tb, anchor=MSO_ANCHOR.MIDDLE)
            _run(tf.paragraphs[0], spec["title"], size=spec["title_size"], color=c["primary"], bold=True, font=self.font_h, cv=cv)
        lay = L["layouts"][spec["layout"]]["slots"]
        for b in spec["blocks"]:
            box = cv.box(lay[b["slot"]])
            getattr(self, "_" + b["type"])(sl, b, box, lay[b["slot"]])
        self._footer(sl, spec)
        self._notes(sl, spec)
        self.n += 1

    def _footer(self, sl, spec):
        cv, c, L = self.cv, self.c, self.L
        x, y, w, h = cv.box(L["footer_box"])
        ln = sl.shapes.add_connector(1, x, Emu(int(y - 6 * cv.sy)), Emu(x + int(1168 * cv.sx)), Emu(int(y - 6 * cv.sy)))
        ln.line.color.rgb = _rgb(c["line"])
        ln.line.width = Pt(0.5)
        st = ln._element.find("{http://schemas.openxmlformats.org/presentationml/2006/main}style")
        if st is not None:
            ln._element.remove(st)
        if spec.get("source_line"):
            tb = sl.shapes.add_textbox(x, y, w, h)
            _run(_frame(tb).paragraphs[0], spec["source_line"], size=11, color=c["muted"], font=self.font_b, cv=cv)
        px, py, pw, ph = cv.box(L["page_box"])
        pb = sl.shapes.add_textbox(px, py, pw, ph)
        p = _frame(pb).paragraphs[0]
        p.alignment = PP_ALIGN.RIGHT
        _run(p, str(self.n + 1), size=11, color=c["muted"], font=self.font_b, cv=cv)

    def _notes(self, sl, spec):
        text = spec.get("notes", "")
        if spec.get("evidence"):
            text += ("\n\n" if text else "") + ("Belege:" if self.lang == "de" else "Evidence:") + "\n" + "\n".join(spec["evidence"])
        if text:
            sl.notes_slide.notes_text_frame.text = text

    # ------------------------------------------------------------ blocks
    def _bullets(self, sl, b, box, raw):
        cv, c = self.cv, self.c
        tb = sl.shapes.add_textbox(*box)
        tf = _frame(tb, margin=fit.PAD * cv.sx * 0.6)
        for i, it in enumerate(b["items"]):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            if it.get("heading"):  # the title of a section that shares the slide: no bullet, bold, in the main colour
                p.space_before = cv.pt(b["size"] * 0.3) if i else cv.pt(0)
                p.space_after = cv.pt(b["size"] * 0.3)
                p.line_spacing = 1.0
                _run(p, it["text"], size=b["size"], color=c["primary"], bold=True, font=self.font_h, cv=cv)
                continue
            sz = b["size"] - (2 if it["level"] else 0)
            _bullet(p, it["level"], sz, cv)
            p.space_after = cv.pt(b["size"] * 0.5)
            p.line_spacing = 1.0
            _run(p, it["text"], size=sz, color=c["text"], font=self.font_b, cv=cv)

    def _kpis(self, sl, b, box, raw):
        cv, c = self.cv, self.c
        x, y, w, h = box
        n, gap = len(b["items"]), int(16 * cv.sx)
        tw = int((w - gap * (n - 1)) / n)
        for i, k in enumerate(b["items"]):
            tx = x + i * (tw + gap)
            _rect(sl, Emu(tx), y, Emu(tw), h, c["soft"])
            _rect(sl, Emu(tx), y, Emu(int(5 * cv.sx)), h, c["accent"])
            tb = sl.shapes.add_textbox(Emu(tx + int(18 * cv.sx)), Emu(y + int(10 * cv.sy)), Emu(tw - int(30 * cv.sx)), Emu(h - int(16 * cv.sy)))
            tf = _frame(tb)
            p = tf.paragraphs[0]
            _run(p, k["value"], size=b["size"], color=c["primary"], bold=True, font=self.font_h, cv=cv)
            if k["unit"]:
                _run(p, " " + k["unit"], size=max(12, b["size"] * 0.4), color=c["muted"], font=self.font_b, cv=cv)
            p2 = tf.add_paragraph()
            _run(p2, k["label"], size=b["label_size"], color=c["text"], font=self.font_b, cv=cv)
            if k.get("delta"):
                p3 = tf.add_paragraph()
                col = {"up": c["good"], "down": c["crit"]}.get(k["tone"], c["muted"])
                _run(p3, k["delta"], size=b["label_size"], color=col, bold=True, font=self.font_b, cv=cv)

    def _callout(self, sl, b, box, raw):
        cv, c = self.cv, self.c
        tone = c[TONES.get(b["tone"], "accent")]
        dark = b["tone"] == "decision"
        _rect(sl, *box, c["primary"] if dark else c["soft"])
        _rect(sl, box[0], box[1], Emu(int(8 * cv.sx)), box[3], tone if not dark else c["accent"])
        tb = sl.shapes.add_textbox(Emu(box[0] + int(28 * cv.sx)), Emu(box[1] + int(14 * cv.sy)), Emu(box[2] - int(48 * cv.sx)), Emu(box[3] - int(28 * cv.sy)))
        tf = _frame(tb, anchor=MSO_ANCHOR.MIDDLE)
        col = c["on_primary"] if dark else c["text"]
        if b["title"]:
            _run(tf.paragraphs[0], b["title"], size=b["size"] * 0.7, color=c["accent"] if dark else tone, bold=True, font=self.font_h, cv=cv)
            p = tf.add_paragraph()
            p.space_before = cv.pt(6)
        else:
            p = tf.paragraphs[0]
        _run(p, b["text"], size=b["size"], color=col, bold=dark, font=self.font_h if dark else self.font_b, cv=cv)

    def _table(self, sl, b, box, raw):
        cv, c = self.cv, self.c
        rows = ([b["header"]] if b["header"] else []) + b["rows"]
        cols = len(rows[0])
        gf = sl.shapes.add_table(len(rows), cols, *box)
        tbl = gf.table
        tblPr = gf._element.graphic.graphicData.tbl.tblPr
        tblPr.set("firstRow", "0")
        tblPr.set("bandRow", "0")
        sid = tblPr.find(f"{{{NS['a']}}}tableStyleId")
        if sid is not None:
            sid.text = "{2D5ABB26-0587-4C30-8999-92F81FD0307C}"  # "No Style, No Grid": every fill and line below is explicit
        def isnum(t: str) -> bool:
            t = t.replace(".", "").replace(",", "").replace(" ", "").replace("%", "").replace("−", "").replace("-", "").replace("+", "")
            return bool(t) and t.isdigit()
        numcol = [all(isnum(r[ci]) or not r[ci] for r in b["rows"]) and any(isnum(r[ci]) for r in b["rows"]) for ci in range(cols)]
        wsum = sum(b["widths"]) or 1
        for ci in range(cols):
            tbl.columns[ci].width = Emu(int(box[2] * b["widths"][ci] / wsum))
        for ri, row in enumerate(rows):
            is_head = bool(b["header"]) and ri == 0
            data_i = ri - (1 if b["header"] else 0)
            hl = b.get("highlight_row") is not None and data_i == b["highlight_row"]
            lines = max(fit.lines(row[ci], b["size"], b["widths"][ci] - 16) for ci in range(cols))
            tbl.rows[ri].height = Emu(int((lines * b["size"] * fit.LINE_H + 14) * cv.sy))
            for ci in range(cols):
                cell = tbl.cell(ri, ci)
                cell.margin_left = cell.margin_right = Emu(int(8 * cv.sx))
                cell.margin_top = cell.margin_bottom = Emu(int(5 * cv.sy))
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                cell.fill.solid()
                cell.fill.fore_color.rgb = _rgb(c["primary"] if is_head else "#E3F4FD" if hl else c["soft"] if data_i % 2 == 1 else c["bg"])
                tf = cell.text_frame
                tf.word_wrap = True
                p = tf.paragraphs[0]
                txt = row[ci]
                p.alignment = PP_ALIGN.RIGHT if numcol[ci] and ci > 0 else PP_ALIGN.LEFT
                _run(p, txt, size=b["size"], color=c["on_primary"] if is_head else c["text"], bold=is_head or hl or ci == 0, font=self.font_b, cv=cv)
                self._cell_border(cell, c["line"])

    @staticmethod
    def _cell_border(cell, color: str):
        tcPr = cell._tc.get_or_add_tcPr()
        for side in ("lnB",):
            ln = etree.SubElement(tcPr, f"{{{NS['a']}}}{side}")
            ln.set("w", "6350")
            sf = etree.SubElement(ln, f"{{{NS['a']}}}solidFill")
            etree.SubElement(sf, f"{{{NS['a']}}}srgbClr").set("val", color.lstrip("#").upper())
        # schema order: borders before fill
        fills = [el for el in tcPr if el.tag.endswith("solidFill")]
        for f in fills:
            tcPr.remove(f)
            tcPr.append(f)

    def _chart(self, sl, b, box, raw):
        cv, c, pal = self.cv, self.c, self.theme["palette"]
        ch = b["chart"]
        x, y, w, h = box
        if ch["title"]:
            tb = sl.shapes.add_textbox(x, y, w, Emu(int(34 * cv.sy)))
            _run(_frame(tb).paragraphs[0], ch["title"] + (f" ({ch['unit']})" if ch["unit"] and ch["unit"] not in ch["title"] else ""), size=17, color=c["text"], bold=True, font=self.font_b, cv=cv)
            y, h = Emu(y + int(36 * cv.sy)), Emu(h - int(36 * cv.sy))
        data = CategoryChartData()
        data.categories = ch["labels"]
        for s in ch["series"]:
            data.add_series(s["name"] or ch["unit"] or " ", s["values"])
        kind = {"column": XL_CHART_TYPE.COLUMN_CLUSTERED, "bar": XL_CHART_TYPE.BAR_CLUSTERED, "line": XL_CHART_TYPE.LINE_MARKERS,
                "donut": XL_CHART_TYPE.DOUGHNUT, "stacked": XL_CHART_TYPE.COLUMN_STACKED}[ch["type"]]
        gf = sl.shapes.add_chart(kind, x, y, w, h, data)
        chart = gf.chart
        chart.has_title = False
        chart.font.size = cv.pt(16)
        chart.font.color.rgb = _rgb(c["text"])
        if self.font_b:
            chart.font.name = self.font_b
        multi = len(ch["series"]) > 1 or ch["type"] == "donut"
        chart.has_legend = multi
        if multi:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
            chart.legend.font.size = cv.pt(16)
        plot = chart.plots[0]
        plot.has_data_labels = True
        dl = plot.data_labels
        dl.font.size = cv.pt(16)
        dl.font.bold = True
        dl.show_value = True
        dl.number_format, dl.number_format_is_linked = "General", False
        if ch["type"] == "donut":
            dl.font.color.rgb = _rgb("#FFFFFF")
            pts = plot.series[0].points
            for i in range(len(ch["labels"])):
                pts[i].format.fill.solid()
                pts[i].format.fill.fore_color.rgb = _rgb(pal[i % len(pal)])
            return
        if ch["type"] != "stacked":
            dl.position = XL_LABEL_POSITION.OUTSIDE_END if ch["type"] in ("column", "bar") else XL_LABEL_POSITION.ABOVE
        for i, s in enumerate(plot.series):
            col = _rgb(pal[i % len(pal)])
            if ch["type"] == "line":
                s.format.line.color.rgb = col
                s.format.line.width = Pt(2.5)
                s.marker.format.fill.solid()
                s.marker.format.fill.fore_color.rgb = col
                s.smooth = False
            else:
                s.format.fill.solid()
                s.format.fill.fore_color.rgb = col if len(ch["series"]) > 1 or ch["highlight"] is None else _rgb(pal[2])
        if ch["highlight"] is not None and len(ch["series"]) == 1 and ch["type"] in ("column", "bar"):
            pt = plot.series[0].points[ch["highlight"]]
            pt.format.fill.solid()
            pt.format.fill.fore_color.rgb = _rgb(pal[0])
        if ch["type"] in ("column", "bar", "stacked"):
            plot.gap_width = 60
        va, ca = chart.value_axis, chart.category_axis
        va.has_major_gridlines = False
        va.visible = False
        if min(v for sr in ch["series"] for v in sr["values"]) >= 0:
            va.minimum_scale = 0  # bars start at zero in the page and in PowerPoint (auto-scaling would cut the axis)
        ca.format.line.color.rgb = _rgb(c["line"])
        ca.tick_labels.font.size = cv.pt(16)
        if ch["type"] == "bar":
            ca.reverse_order = True

    def _image(self, sl, b, box, raw, data: bytes | None = None):
        # images are put in by `place_image` once the bytes are known (the spec only names the asset)
        pass

    def place_image(self, sl_index: int, slot: dict, data: bytes, caption: str):
        from PIL import Image

        sl = self.prs.slides[sl_index]
        cv = self.cv
        x, y, w, h = cv.box(slot)
        with Image.open(io.BytesIO(data)) as im:
            iw, ih = im.size
        room = h - int(32 * cv.sy) if caption else h
        k = min(w / iw, room / ih)
        pw, ph = int(iw * k), int(ih * k)
        sl.shapes.add_picture(io.BytesIO(data), Emu(x + int((w - pw) / 2)), y, Emu(pw), Emu(ph))
        if caption:
            tb = sl.shapes.add_textbox(x, Emu(y + ph + int(6 * cv.sy)), w, Emu(int(26 * cv.sy)))
            _run(_frame(tb).paragraphs[0], caption, size=11, color=self.c["muted"], font=self.font_b, cv=cv)

    def save(self) -> bytes:
        out = io.BytesIO()
        self.prs.save(out)
        return out.getvalue()


def build_pptx(specs: list[dict], *, template: bytes | None = None, lang: str = "de", images: dict[str, bytes] | None = None) -> bytes:
    """specs: normalised slide specs (the first may be of kind 'title'). images: asset id -> bytes for image blocks."""
    d = Deck(template, lang)
    L = layouts()
    for i, spec in enumerate(specs):
        d.slide(spec)
        for b in spec["blocks"]:
            if b["type"] == "image" and images and b["asset_id"] in images:
                d.place_image(len(d.prs.slides) - 1, L["layouts"][spec["layout"]]["slots"][b["slot"]], images[b["asset_id"]], b.get("caption", ""))
    return d.save()
