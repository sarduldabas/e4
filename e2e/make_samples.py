"""Creates a small, consistent set of sample files for the demo and the end-to-end test.
Topic: dual sourcing of battery cells. The numbers are the same in every file, so the checks have something to find."""
from __future__ import annotations

import io
from pathlib import Path


def make_template() -> bytes:
    from pptx import Presentation
    prs = Presentation()
    titles = ["FAKOM Standard Template", "Management Summary", "Hintergrund und Umfang", "Optionen und Kosten", "Risiken und Gegenmaßnahmen",
              "Zeitplan und Meilensteine", "Empfehlung und nächste Schritte", "Vielen Dank"]
    for i, t in enumerate(titles):
        layout = prs.slide_layouts[0 if i in (0, len(titles) - 1) else 1]
        s = prs.slides.add_slide(layout)
        s.shapes.title.text = t
        if i not in (0, len(titles) - 1):
            s.placeholders[1].text = "Platzhalter"
    out = io.BytesIO()
    prs.save(out)
    return out.getvalue()


def make_offer_docx() -> bytes:
    import docx
    d = docx.Document()
    d.add_heading("Angebotsvergleich Batteriezellen", 1)
    d.add_paragraph("Die Lieferantenlandschaft für Hochvolt-Batteriezellen umfasst heute zwei Lieferanten: Nordcell liefert 70 % des Volumens, Sunvolt liefert 30 % des Volumens.")
    d.add_paragraph("Option A (Dual Sourcing mit Sunvolt als zweitem Lieferanten) kostet 12 Mio € über 24 Monate.")
    d.add_paragraph("Option B (Dual Sourcing mit einem neuen Lieferanten) kostet 15,5 Mio € über 24 Monate.")
    d.add_paragraph("Option C (Eigenfertigung) kostet 18 Mio € über 36 Monate.")
    d.add_paragraph("Hintergrund: Der Rahmenvertrag mit Nordcell läuft Ende 2027 aus. Ein einzelner Lieferant stellt ein Versorgungsrisiko dar.")
    t = d.add_table(rows=4, cols=3)
    for r, row in enumerate([["Option", "Kosten (Mio €)", "Laufzeit (Monate)"], ["A", "12", "24"], ["B", "15,5", "24"], ["C", "18", "36"]]):
        for c, v in enumerate(row):
            t.cell(r, c).text = v
    out = io.BytesIO()
    d.save(out)
    return out.getvalue()


def make_cost_xlsx() -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Kosten"
    ws.append(["Position", "Option A (Mio €)", "Option B (Mio €)", "Option C (Mio €)"])
    ws.append(["Werkzeuge", 4, 6, 9])
    ws.append(["Qualifizierung", 3, 4.5, 4])
    ws.append(["Anlauf und Logistik", 5, 5, 5])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


RISKS = """# Risiken Dual Sourcing

Das Risiko eines Lieferverzugs von bis zu 3 Monaten beim zweiten Lieferanten wird als hoch eingestuft.
Gegenmaßnahme: ein Sicherheitsbestand für 8 Wochen wird aufgebaut.

Das Qualitätsrisiko bei der Qualifizierung neuer Zellen wird als mittel eingestuft. Gegenmaßnahme: gemeinsame Audits mit dem Lieferanten.
"""

PLAN = """Projektplan Dual Sourcing

Meilenstein 1: Vertragsabschluss mit dem zweiten Lieferanten bis 15.01.2027.
Meilenstein 2: Qualifizierung der Zellen bis 30.09.2027.
Meilenstein 3: Serienanlauf im Januar 2028.
Die Entscheidung des Gremiums wird am 03.12.2026 erwartet.
"""


def write_all(folder: Path) -> dict[str, Path]:
    folder.mkdir(parents=True, exist_ok=True)
    files = {"template.pptx": make_template(), "Angebote_Batteriezellen.docx": make_offer_docx(), "Kostenmodell_Dual_Sourcing.xlsx": make_cost_xlsx(),
             "Risiken_Dual_Sourcing.md": RISKS.encode("utf-8"), "Projektplan_Dual_Sourcing.txt": PLAN.encode("utf-8"),
             "Urlaubsplanung.txt": "Urlaubsplanung Sommer: Team Ost vom 1. bis 14. Juli, Team West vom 15. bis 28. Juli.".encode("utf-8")}
    out = {}
    for name, data in files.items():
        p = folder / name
        p.write_bytes(data)
        out[name] = p
    return out


if __name__ == "__main__":
    import sys
    dst = Path(sys.argv[1] if len(sys.argv) > 1 else "sample-data")
    for n, p in write_all(dst).items():
        print(p)
