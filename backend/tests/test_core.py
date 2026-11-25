import io

import pytest

from app.core.calc import CalcError, evaluate
from app.core.deck import SlideSpec, build_deck
from app.core.parsers import parse_bytes, read_template
from app.core.storage import LocalFileStore, safe_name

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "e2e"))
from make_samples import make_cost_xlsx, make_offer_docx, make_template  # noqa: E402


def test_calc_evaluates_and_refuses_anything_else():
    assert evaluate("max(a, b) - min(a, b)", {"a": 12, "b": 15.5}) == 3.5
    assert evaluate("round(a / b * 100, 1)", {"a": 1, "b": 3}) == 33.3
    for bad in ["__import__('os')", "a.real", "a / 0", "2 ** 99", "x + 1", "lambda: 1", "[1]", "sum()"]:
        with pytest.raises(CalcError):
            evaluate(bad, {"a": 1})


def test_parse_docx_keeps_numbers_tables_and_locators():
    p = parse_bytes("a.docx", make_offer_docx())
    text = " ".join(c.text for c in p.chunks)
    assert "15,5 Mio €" in text and any(c.locator.startswith("Tabelle") for c in p.chunks) and p.tables and p.title


def test_parse_xlsx_rows_become_quotable_text():
    p = parse_bytes("k.xlsx", make_cost_xlsx())
    assert p.chunks[0].locator.startswith("Blatt „Kosten“") and "Werkzeuge | 4 | 6 | 9" in p.chunks[0].text


def test_parse_text_formats_and_unsupported():
    assert "Betreff: Preis" in parse_bytes("m.eml", b"From: a@b.c\nSubject: Preis\n\nHallo 12 Mio").chunks[0].text
    assert parse_bytes("p.csv", "a;b\n1;2\n".encode()).tables[0].rows[1] == ["1", "2"]
    assert "Gewinn" in parse_bytes("p.html", "<html><title>T</title><script>x</script><p>Gewinn 5</p></html>".encode()).chunks[0].text
    with pytest.raises(ValueError):
        parse_bytes("x.exe", b"MZ")


def test_template_reader_and_deck_roundtrip():
    t = read_template(make_template(), "t")
    assert t["slide_count"] == 8 and "Title and Content" in t["layouts"] and t["slides"][1]["title"] == "Management Summary"
    data = build_deck([SlideSpec("Titel A", ["x 12 Mio €"], "Notiz", chart={"type": "column", "title": "K", "unit": "M€", "labels": ["A", "B"], "values": [1, 2]}),
                       SlideSpec("Tabelle", ["y"], table=[["a", "b"], ["1", "2"]], footer="Quellen: s")], template=make_template(), title="T", subtitle="S")
    p = parse_bytes("d.pptx", data)
    assert [c.locator.split(" (")[0] for c in p.chunks if "Notizen" not in c.locator] == ["Folie 1", "Folie 2", "Folie 3"]  # the template's own slides are gone
    assert any("Notiz" in c.text and "Notizen" in c.locator for c in p.chunks)


def test_file_store_blocks_path_traversal(tmp_path):
    st = LocalFileStore(tmp_path)
    st.put("a/b.txt", b"x")
    assert st.get("a/b.txt") == b"x"
    with pytest.raises(ValueError):
        st.get("../outside")
    assert safe_name("..\\..\\evil name?.pptx") == "evil name_.pptx"
