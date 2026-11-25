"""Research planning, web research by default, and the asset library (figures cut out of PDFs, chart data as evidence, user's choice)."""
import io
import sys
from pathlib import Path

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Inches

from app.core.ingest import parse_bytes
from app.core.ingest.figures import crop_fraction
from app.models import Asset, Evidence

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_pipeline import case, research  # noqa: E402,F401


def _pdf_with_chart() -> bytes:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    fig, ax = plt.subplots(figsize=(6, 3.2))
    ax.bar(["2024", "2025", "2026"], [12, 15, 19])
    ax.set_title("Kosten in Mio. EUR")
    png = io.BytesIO()
    fig.savefig(png, format="png", dpi=160)
    out = io.BytesIO()
    c = canvas.Canvas(out)
    c.setFont("Helvetica", 11)
    for i in range(7):
        c.drawString(60, 780 - i * 14, "Die Kosten der Datenaufbereitung steigen in den Jahren 2024 bis 2026 deutlich an.")
    c.drawImage(ImageReader(io.BytesIO(png.getvalue())), 60, 420, width=470, height=250)
    c.drawString(60, 400, "Abbildung 1: Kostenentwicklung 2024 bis 2026")
    for i in range(5):
        c.drawString(60, 370 - i * 14, "Weiterer Text nach der Abbildung mit Erläuterungen.")
    c.save()
    return out.getvalue()


def _pptx_with_chart() -> bytes:
    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Kostenentwicklung"
    cd = CategoryChartData()
    cd.categories = ["2024", "2025", "2026"]
    cd.add_series("Kosten", (12.0, 15.0, 19.0))
    s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1.5), Inches(6), Inches(4), cd)
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


def test_pdf_figure_is_cut_out_with_its_caption():
    p = parse_bytes("bericht.pdf", _pdf_with_chart())
    assert len(p.images) == 1
    im = p.images[0]
    assert im.caption.startswith("Abbildung 1") and "Weiterer Text" not in im.caption
    assert im.width > 600 and im.locator == "S. 1" and "Kosten" in im.context


def test_pptx_chart_keeps_its_exact_numbers():
    p = parse_bytes("deck.pptx", _pptx_with_chart())
    assert len(p.charts) == 1
    ch = p.charts[0]
    assert ch.labels == ["2024", "2025", "2026"] and ch.series[0]["values"] == [12.0, 15.0, 19.0] and ch.type == "column"


def test_crop_fraction_cuts_the_box_and_refuses_tiny_ones():
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (400, 300), "white").save(buf, "PNG")
    data, w, h = crop_fraction(buf.getvalue(), (0.25, 0.25, 0.75, 0.75))
    assert (w, h) == (200, 150)
    assert crop_fraction(buf.getvalue(), (0.0, 0.0, 0.05, 0.05)) is None


def test_web_research_is_on_by_default_and_the_plan_is_recorded(case):
    c, rid, base = case
    assert c.get(f"{base}/case").json()["use_web"] is True
    research(c, base)
    plan = c.get(f"{base}/research-plan").json()
    assert plan["rounds"], "the planner's decisions are kept"
    first = plan["rounds"][0]
    assert first["mode"] == "initial" and first["strategy"]
    assert any(q["kind"] == "web" for q in first["queries"])  # planned although no model is available
    assert first["result"]["web"] is True
    assert plan["web_notes"], "without a model the search cannot run: that is said, not hidden"


def test_chart_numbers_of_an_uploaded_deck_enter_the_ledger_and_the_library(case):
    c, rid, base = case
    assert c.post(f"{base}/files", files={"file": ("Kosten.pptx", _pptx_with_chart())}, data={"role": "source"}).status_code == 201
    research(c, base)
    with c.app.state.db.session() as s:
        rows = s.query(Evidence).filter(Evidence.report_id == rid, Evidence.locator.like("Diagramm:%"), Evidence.kind == "number").all()
        assert sorted(r.value for r in rows) == [12.0, 15.0, 19.0]
        assert all(r.period in ("2024", "2025", "2026") for r in rows)
    lib = c.get(f"{base}/assets").json()
    chart = next(a for a in lib if a["kind"] == "chart")
    assert chart["has_data"] and chart["treatment"] == "redraw" and not chart["has_image"]


def test_user_choice_beats_the_curator_and_images_are_served(case, tmp_path):
    c, rid, base = case
    assert c.post(f"{base}/files", files={"file": ("Bericht.pdf", _pdf_with_chart())}, data={"role": "source"}).status_code == 201
    research(c, base)
    lib = c.get(f"{base}/assets").json()
    img = next(a for a in lib if a["kind"] == "image" and a["origin"] == "document" and a["caption"].startswith("Abbildung 1"))
    assert c.get(f"{base}/assets/{img['id']}").headers["content-type"] == "image/png"
    assert c.patch(f"{base}/assets/{img['id']}", json={"user_choice": "skip"}).status_code == 200
    now = next(a for a in c.get(f"{base}/assets").json() if a["id"] == img["id"])
    assert now["user_choice"] == "skip" and now["chosen"] is False
    assert c.patch(f"{base}/assets/{img['id']}", json={"user_choice": "use", "section_key": "optionen-und-kosten"}).status_code == 200
    now = next(a for a in c.get(f"{base}/assets").json() if a["id"] == img["id"])
    assert now["chosen"] is True and now["section_key"] == "optionen-und-kosten"
    assert c.patch(f"{base}/assets/{img['id']}", json={"user_choice": "maybe"}).status_code in (400, 422)
    assert c.patch(f"{base}/assets/a-nope", json={"user_choice": "use"}).status_code == 404


def test_vision_result_crops_and_turns_a_chart_into_evidence(case):
    """The asset-analyst's answer is applied by code: the crop becomes an asset of its own, chart data becomes evidence."""
    from app.services import assets as assets_svc

    c, rid, base = case
    c.post(f"{base}/files", files={"file": ("Bericht.pdf", _pdf_with_chart())}, data={"role": "source"})
    research(c, base)
    ctx = c.app.state.ctx
    with ctx.db.session() as s:
        a = next(x for x in s.query(Asset).filter_by(report_id=rid, kind="image").all() if x.origin == "document")
        aid = a.id
        a.analysed = False  # look at it again, with a model that finds the figure and reads the chart
    real = ctx.runner

    class Vision:
        def __getattr__(self, n):
            return getattr(real, n)

        def run(self, agent, payload, report_id=None):
            if agent != "asset-analyst":
                return real.run(agent, payload, report_id=report_id)
            return {"assets": [{"id": x["id"], "role": "chart", "description": "Säulendiagramm Kosten 2024-2026", "text": "Kosten in Mio. EUR", "legibility": 0.9,
                                "crop": {"x0": 0.1, "y0": 0.1, "x1": 0.9, "y1": 0.9}, "treatment": "redraw", "reason": "Diagramm", "section_keys": ["optionen-und-kosten"],
                                "chart": {"type": "column", "title": "Kosten", "unit": "Mio. EUR", "labels": ["2024", "2025", "2026"], "series": [{"name": "Kosten", "values": [12, 15, 19]}], "printed": True}}
                               for x in payload["assets"]]}

    ctx.runner = Vision()
    try:
        sections = [{"key": "optionen-und-kosten", "title": "Optionen und Kosten", "purpose": "", "required_inputs": []}]
        stats = assets_svc.assess(ctx, rid, {"lang": "de", "topic": "Kosten"}, sections)
        assert stats["cropped"] >= 1 and stats["charts"] >= 1
        assert assets_svc.chart_evidence(ctx, rid, sections) >= 4
    finally:
        ctx.runner = real
    with ctx.db.session() as s:
        orig = s.get(Asset, aid)
        child = s.query(Asset).filter_by(report_id=rid, parent_id=aid).first()
        assert orig.treatment == "discard" and child and child.origin == "crop" and child.width < orig.width
        ev = s.query(Evidence).filter(Evidence.report_id == rid, Evidence.kind == "number", Evidence.statement.like("Kosten: 2025%")).first()
        assert ev and ev.value == 15.0 and ev.unit == "Mio. EUR" and ev.section_key == "optionen-und-kosten"
