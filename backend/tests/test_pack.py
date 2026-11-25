"""Which short slides share a page in the file, and that the combined page keeps every point and every claim link."""
import io

from pptx import Presentation

from app.core.slides import build_pptx, merge, normalise, pack_plan
from app.core.slides.pack import text_fill


def slide(title, points, kind="content", layout="bullets"):
    sp, _ = normalise({"kind": kind, "layout": layout, "title": title,
                       "blocks": [{"slot": "bullets", "type": "bullets", "items": [{"text": p, "claim_ids": [f"k-{title[:3]}{i}"]} for i, p in enumerate(points)]}]})
    return sp


def test_short_text_slides_of_different_sections_share_a_page_and_full_ones_do_not():
    short_a, short_b = slide("Zeitplan klar", ["Start im Mai", "Ende im Oktober"]), slide("Risiken überschaubar", ["Lieferengpass möglich", "Preis schwankt"])
    full = slide("Optionen", [("Ein sehr langer Punkt über die Kosten der Optionen mit allen Details und Annahmen. " * 3)[:225]] * 7)
    assert text_fill(short_a) < 0.4 and text_fill(full) > 0.75
    assert pack_plan([short_a, short_b], ["zeit", "risiko"]) == [[0, 1]]
    assert pack_plan([full, short_b], ["optionen", "risiko"]) == [[0], [1]]  # a page that is three quarters full starts the next section on a new slide
    assert pack_plan([short_a, short_b], ["zeit", "zeit"]) == [[0], [1]]  # two slides of one section stay as the writer made them


def test_slides_with_charts_tables_or_a_special_kind_are_never_merged():
    short = slide("Kurz", ["Nur ein Punkt"])
    chart, _ = normalise({"layout": "chart-text", "title": "Diagramm", "blocks": [{"slot": "chart", "type": "chart", "chart": {"type": "column", "labels": ["a", "b"], "series": [{"name": "x", "values": [1, 2]}]}}]})
    summary = slide("Zusammenfassung", ["Punkt"], kind="summary")
    assert pack_plan([short, chart, short], ["a", "b", "c"]) == [[0], [1], [2]]
    assert pack_plan([summary, short], ["_summary", "a"]) == [[0], [1]]


def test_merged_page_keeps_every_point_and_claim_link_and_draws_headings():
    a, b = slide("Zeitplan klar", ["Start im Mai", "Ende im Oktober"]), slide("Risiken überschaubar", ["Lieferengpass möglich"])
    m, _ = normalise(merge([a, b], ["Zeitplan", "Risiken"]))
    items = m["blocks"][0]["items"]
    assert m["title"] == "Zeitplan · Risiken"
    assert [i["text"] for i in items if i.get("heading")] == ["Zeitplan klar", "Risiken überschaubar"]
    assert [i["text"] for i in items if not i.get("heading")] == ["Start im Mai", "Ende im Oktober", "Lieferengpass möglich"]
    assert {c for i in items for c in i["claim_ids"]} == {"k-Zei0", "k-Zei1", "k-Ris0"}
    prs = Presentation(io.BytesIO(build_pptx([m])))
    text = "\n".join(sh.text_frame.text for sh in prs.slides[0].shapes if sh.has_text_frame)
    assert "Zeitplan klar" in text and "Lieferengpass möglich" in text
