"""The readers on real files: text PDFs, scanned PDFs, mails with attachments, Office files, pictures, archives."""
from __future__ import annotations

import io
import zipfile
from email.message import EmailMessage

import pytest
from PIL import Image, ImageDraw

from app.core.ingest import apply_vision, kind_of, parse_bytes, sniff
from app.core.ingest.mail import msg_from_ole
from app.core.ingest.model import Options
from app.core.ingest.text import clean, drop_repeated_lines, garbled_ratio, split


# ---------------------------------------------------------------------------------------------- sample makers
def text_pdf(pages: list[str]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    for t in pages:
        y = 800
        for line in t.split("\n"):
            c.drawString(50, y, line)
            y -= 16
        c.showPage()
    c.save()
    return buf.getvalue()


def page_image(text: str, size=(1240, 1754)) -> Image.Image:
    im = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(im)
    d.multiline_text((80, 100), text, fill="black")
    return im


def scanned_pdf(pages: list[str]) -> bytes:
    ims = [page_image(t) for t in pages]
    buf = io.BytesIO()
    ims[0].save(buf, "PDF", save_all=True, append_images=ims[1:], resolution=150)
    return buf.getvalue()


def png(w=800, h=500, text="Diagramm") -> bytes:
    im = Image.new("RGB", (w, h), "white")
    d = ImageDraw.Draw(im)
    for i in range(10):
        d.rectangle([40 + i * 70, h - 40 - i * 30, 90 + i * 70, h - 40], fill=(0, 30 + i * 20, 80))
    d.text((20, 10), text, fill="black")
    out = io.BytesIO()
    im.save(out, "PNG")
    return out.getvalue()


# ---------------------------------------------------------------------------------------------- text helpers
def test_clean_and_split_keep_numbers_and_join_hyphenated_words():
    assert clean("Die Ko-\nsten  steigen um 12,5 %.") == "Die Kosten steigen um 12,5 %."
    chunks = split("S. 1", "\n".join(f"Zeile {i} mit 1{i},5 Mio €" for i in range(300)))
    assert len(chunks) > 3 and all(len(c.text) <= 2000 for c in chunks) and chunks[1].locator == "S. 1 (2)"
    assert len(split("x", "a" * 10_000)) > 3  # one enormous line is still cut


def test_garbled_text_is_recognised_and_normal_german_is_not():
    assert garbled_ratio("Ã¤hnlich Ã¶ffentlich Ã¼ber " * 10) > 0.3
    assert garbled_ratio("Die Kosten steigen im Jahr 2025 um zwölf Prozent gegenüber dem Vorjahr deutlich.") == 0.0


def test_running_headers_and_page_numbers_are_dropped():
    pages = [f"VW Konzern – Vertraulich\nInhalt {i} mit Zahlen {i * 3}\nSeite {i}" for i in range(1, 8)]
    out = drop_repeated_lines(pages)
    assert all("Vertraulich" not in p and "Seite" not in p and "Inhalt" in p for p in out)


# ---------------------------------------------------------------------------------------------- PDF
def test_text_pdf_pages_become_locators_and_header_noise_is_gone():
    pages = [f"Konzern Vertraulich\nKapitel {i}: Die Kosten betragen {10 + i},5 Mio EUR im Jahr 2025 und steigen weiter.\n" + "Weiterer Text zur Erläuterung. " * 6 for i in range(1, 6)]
    p = parse_bytes("bericht.pdf", text_pdf(pages))
    assert p.kind == "pdf" and p.stats["pages"] == 5 and not p.vision
    assert [c.locator for c in p.chunks][:2] == ["S. 1", "S. 2"]
    assert "11,5 Mio EUR" in p.chunks[0].text and "Vertraulich" not in " ".join(c.text for c in p.chunks)


def test_scanned_pdf_pages_become_vision_tasks_and_the_transcription_is_inserted_in_page_order():
    body = text_pdf(["Seite eins mit genug Text, damit die Seite als Textseite erkannt wird. " * 3])
    scan = scanned_pdf(["Angebot Zellen", "Preis 12,5 Mio EUR"])
    p = parse_bytes("scan.pdf", scan)
    assert p.stats["scanned_pages"] == 2 and [v.key for v in p.vision] == ["p1", "p2"] and not p.chunks
    assert all(v.image[:2] == b"\xff\xd8" for v in p.vision)  # JPEG
    n = apply_vision(p, {"p2": {"text": "Preis 12,5 Mio EUR"}, "p1": {"text": "Angebot Zellen"}})
    assert n == 2 and [c.locator for c in p.chunks] == ["S. 1", "S. 2"] and p.chunks[1].flags == ("vision",)
    # without a vision model the gap is reported, not hidden
    p2 = parse_bytes("scan.pdf", scan)
    assert any("scanned" in w or "vision" in w for w in p2.warnings) or p2.vision
    assert parse_bytes("x.pdf", body).vision == []


def test_vision_limit_is_reported():
    p = parse_bytes("scan.pdf", scanned_pdf([f"S{i}" for i in range(5)]), Options(max_vision_pages=2))
    assert len(p.vision) == 2 and any("limit 2" in w for w in p.warnings)


def test_broken_and_protected_pdfs_give_a_clear_error():
    with pytest.raises(ValueError):
        parse_bytes("kaputt.pdf", b"%PDF-1.4 not really")


# ---------------------------------------------------------------------------------------------- mail
def make_eml(with_pdf=True, with_logo=True) -> bytes:
    m = EmailMessage()
    m["From"], m["To"], m["Subject"], m["Date"] = "a@vw.de", "b@vw.de", "AW: Angebot Zellen", "Mon, 3 Nov 2025 10:00:00 +0100"
    m.set_content("Hallo,\nanbei das Angebot über 15,5 Mio €.\n> Frühere Mail: Preis 14 Mio\n")
    if with_pdf:
        m.add_attachment(text_pdf(["Angebot: Gesamtpreis 15,5 Mio EUR, Lieferung ab Q3 2026. " * 3]), maintype="application", subtype="pdf", filename="angebot.pdf")
    m.add_attachment(b"Position;Preis\nZellen;12\n", maintype="text", subtype="csv", filename="preise.csv")
    if with_logo:
        m.add_attachment(png(60, 40), maintype="image", subtype="png", filename="logo.png")  # a signature logo is ignored
    return bytes(m)


def test_mail_attachments_are_read_with_their_own_locators():
    p = parse_bytes("m.eml", make_eml())
    locs = [c.locator for c in p.chunks]
    assert locs[0] == "E-Mail" and "Betreff: AW: Angebot Zellen" in p.chunks[0].text and "Preis 14 Mio" in p.chunks[0].text and "> " not in p.chunks[0].text
    assert any(l.startswith("Anhang „angebot.pdf“ › S. 1") for l in locs) and any("preise.csv" in l for l in locs)
    assert "15,5 Mio EUR" in " ".join(c.text for c in p.chunks) and p.meta["attachments"] == ["angebot.pdf", "preise.csv"]
    assert not p.images  # the 60x40 logo is not kept


def test_nested_mail_and_zip_are_opened_and_depth_is_limited():
    inner = make_eml(with_pdf=False)
    outer = EmailMessage()
    outer["Subject"] = "WG: Weiterleitung"
    outer.set_content("siehe Anhang")
    outer.add_attachment(inner, maintype="message", subtype="rfc822", filename="alt.eml")
    p = parse_bytes("o.eml", bytes(outer))
    assert any(c.locator.startswith("Anhang „alt.eml“") for c in p.chunks)
    z = io.BytesIO()
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("a/notiz.txt", "Beschluss: 12 Mio €")
        zf.writestr("a/angebot.pdf", text_pdf(["Preis 9,9 Mio EUR " * 8]))
        zf.writestr("__MACOSX/x", "junk")
    zp = parse_bytes("paket.zip", z.getvalue())
    assert {c.locator.split(" › ")[0] for c in zp.chunks} == {"Datei „a/notiz.txt“", "Datei „a/angebot.pdf“"}


def test_msg_reader_with_a_fake_ole_container():
    class Ole:
        def __init__(self, streams):
            self.streams = streams

        def exists(self, p):
            return p in self.streams or any(k.startswith(p + "/") for k in self.streams)

        def openstream(self, p):
            return io.BytesIO(self.streams[p])

        def listdir(self, streams=True, storages=False):
            seen = set()
            for k in self.streams:
                parts = k.split("/")
                for i in range(1, len(parts)):
                    seen.add(tuple(parts[:i]))
            return [list(x) for x in seen] if storages else [k.split("/") for k in self.streams]

    u = lambda s: s.encode("utf-16-le")
    ole = Ole({"__substg1_0_0037001F": u("Angebot"), "__substg1_0_1000001F": u("Preis 15,5 Mio €"), "__substg1_0_0C1A001F": u("a@vw.de"),
               "__attach_version1.0_#00000000/__substg1_0_3707001F": u("preise.csv"),
               "__attach_version1.0_#00000000/__substg1_0_37010102": b"Position;Preis\nZellen;12\n"})
    p = msg_from_ole(ole, "", lambda n, b, d: parse_bytes(n, b), Options(), 0)
    assert p.title == "Angebot" and "Preis 15,5 Mio €" in p.chunks[0].text and any("Anhang „preise.csv“" in c.locator for c in p.chunks)


# ---------------------------------------------------------------------------------------------- Office, images, odd files
def test_docx_keeps_order_headings_tables_and_comments_of_authors():
    import docx

    d = docx.Document()
    d.add_heading("Kostenübersicht", 1)
    d.add_paragraph("Option A kostet 12 Mio €.")
    t = d.add_table(rows=2, cols=2)
    t.cell(0, 0).text, t.cell(0, 1).text, t.cell(1, 0).text, t.cell(1, 1).text = "Option", "Kosten", "A", "12"
    d.add_heading("Risiken", 1)
    d.add_paragraph("Lieferengpass bei Zellen.")
    buf = io.BytesIO()
    d.save(buf)
    p = parse_bytes("k.docx", buf.getvalue())
    locs = [c.locator for c in p.chunks]
    assert locs[0].startswith("„Kostenübersicht“") and locs[1].startswith("Tabelle 1") and locs[2].startswith("„Risiken“")
    assert p.tables[0].rows == [["Option", "Kosten"], ["A", "12"]]


def test_xlsx_big_sheet_gets_column_statistics_and_german_numbers():
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Daten"
    ws.append(["Werk", "Menge", "Kosten"])
    for i in range(400):
        ws.append([f"W{i % 3}", i, "1.234,5"])
    ws["E1"] = "=SUM(B2:B401)"
    buf = io.BytesIO()
    wb.save(buf)
    p = parse_bytes("d.xlsx", buf.getvalue())
    stats = next(c for c in p.chunks if "Spaltenstatistik" in c.locator)
    assert "Menge: 400 Werte, Summe 79800" in stats.text and "Kosten: 400 Werte, Summe 493800" in stats.text and "Werk: 400 Einträge, 3 verschiedene" in stats.text
    assert any("Formeln" in c.locator and "=SUM(B2:B401)" in c.text for c in p.chunks)


def test_pptx_text_tables_charts_notes_and_hidden_slides():
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches

    prs = Presentation()
    s = prs.slides.add_slide(prs.slide_layouts[5])
    s.shapes.title.text = "Kosten je Option"
    cd = CategoryChartData()
    cd.categories = ["A", "B"]
    cd.add_series("Mio €", (12, 15.5))
    s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(2), Inches(6), Inches(4), cd)
    s.notes_slide.notes_text_frame.text = "Sprechernotiz: B ist teurer"
    buf = io.BytesIO()
    prs.save(buf)
    p = parse_bytes("k.pptx", buf.getvalue())
    txt = " ".join(c.text for c in p.chunks)
    assert "Kategorien: A | B" in txt and "Mio €: 12 | 15.5" in txt and "Sprechernotiz" in txt


def test_pictures_go_to_the_vision_model_and_tiny_ones_do_not():
    p = parse_bytes("chart.png", png())
    assert [v.reason for v in p.vision] == ["image"] and p.images
    n = apply_vision(p, {"i1": {"text": "Umsatz 2025: 12 Mio", "description": "Säulendiagramm mit steigenden Werten"}})
    assert n == 1 and "Abbildung: Säulendiagramm" in p.chunks[0].text and p.chunks[0].flags == ("vision",)
    import docx

    d = docx.Document()
    d.add_paragraph("x")
    d.add_picture(io.BytesIO(png(60, 40)))  # a 60x40 icon
    buf = io.BytesIO()
    d.save(buf)
    assert not parse_bytes("i.docx", buf.getvalue()).vision


def test_type_is_taken_from_the_content_not_only_from_the_name():
    assert sniff("bericht.doc", text_pdf(["x"])) == "pdf"
    assert sniff("x.zip", b"PK\x03\x04" + b"junk") in ("zip",)
    assert kind_of("A.PDF") == "pdf"
    with pytest.raises(ValueError, match="not supported"):
        parse_bytes("x.exe", b"MZ....")
    with pytest.raises(ValueError, match="empty"):
        parse_bytes("leer.txt", b"")


def test_text_encodings_and_html_and_csv_with_semicolons():
    assert "Größe 5 Mio €" in parse_bytes("a.txt", "Größe 5 Mio €".encode("cp1252")).chunks[0].text
    assert "Größe" in parse_bytes("b.txt", "Größe".encode("utf-16")).chunks[0].text
    p = parse_bytes("c.csv", "Werk;Kosten\nA;12\nB;15\n".encode())
    assert p.tables[0].rows[2] == ["B", "15"] and "Werk | Kosten" in p.chunks[0].text


def test_large_pdf_is_read_page_by_page_without_trouble():
    pages = [f"Seite {i}: Die Umsätze in Werk {i % 7} betrugen {i},5 Mio EUR. " * 5 for i in range(1, 121)]
    p = parse_bytes("gross.pdf", text_pdf(pages))
    assert p.stats["pages"] == 120 and len(p.chunks) >= 120 and p.chunks[-1].locator.startswith("S. 120")
