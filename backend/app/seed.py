"""Demo master data, same content as the front-end prototype."""

COMMITTEES = [
    {"id": "fakom", "name": "FAKOM", "date": "2026-12-03", "template": "FAKOM standard template · 12 slides", "has_report": True},
    {"id": "tsc", "name": "Technical Steering Committee", "date": "2026-12-17", "template": "Committee standard template · 10 slides", "has_report": False},
    {"id": "ic", "name": "Investment Committee", "date": "2027-01-14", "template": "Investment template · 14 slides", "has_report": False},
]

REPORTS = [
    {"id": "r1", "title": "Dual-sourcing strategy for high-voltage battery cells", "committee": "FAKOM", "date": "2026-12-03", "version": "v2",
     "status": "Draft", "stage": 2, "edited": "Today, 23:41", "people": ["kw", "jm", "ls"], "workspace": None},
    {"id": "r2", "title": "Module supply: volume split and review gate", "committee": "FAKOM", "date": "2025-06-18", "version": "v1",
     "status": "Decided", "stage": 3, "edited": "18.06.2025", "people": ["kw", "ls"], "workspace": None},
    {"id": "r3", "title": "Charging partner shortlist", "committee": "Technical Steering Committee", "date": "2026-10-08", "version": "v3",
     "status": "Presented", "stage": 3, "edited": "09.10.2026", "people": ["kw", "jm"], "workspace": None},
]
