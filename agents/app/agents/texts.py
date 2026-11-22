"""All user-visible agent text, German (default) and English. Formal register (Sie)."""

LABELS = {
    "getting_started": {"de": "Am Anfang", "en": "Getting started"},
    "good_basis": {"de": "Gute Basis", "en": "Good basis"},
    "strong_brief": {"de": "Starkes Briefing", "en": "Strong brief"},
    "excellent_brief": {"de": "Ausgezeichnetes Briefing", "en": "Excellent brief"},
}

BREAKDOWN = {
    "topic": {"de": "Thema", "en": "Topic"},
    "committee": {"de": "Gremium", "en": "Committee"},
    "date": {"de": "Termin", "en": "Date"},
    "description": {"de": "Beschreibung", "en": "Description"},
    "material": {"de": "Material", "en": "Material"},
    "sources": {"de": "Quellen", "en": "Sources"},
    "answers": {"de": "Antworten", "en": "Answers"},
}

HINTS = {
    "topic": {
        "de": "Nennen Sie das Thema in einem Satz",
        "en": "Name the topic in one sentence",
    },
    "committee_date": {
        "de": "Sagen Sie, für welches Gremium und welchen Termin der Bericht ist",
        "en": "Say which committee and which date the report is for",
    },
    "committee": {
        "de": "Sagen Sie, für welches Gremium der Bericht ist",
        "en": "Say which committee the report is for",
    },
    "date": {
        "de": "Ergänzen Sie den Gremiumstermin",
        "en": "Add the committee date",
    },
    "description": {
        "de": "Sagen Sie ein paar Sätze dazu, was Sie wissen und was Sie erwarten",
        "en": "Say a few sentences about what you know and what you expect",
    },
    "material": {
        "de": "Fügen Sie die wichtigsten Dokumente, E-Mails und früheren Berichte hinzu",
        "en": "Add the key documents, mails and previous reports",
    },
    "outlook": {
        "de": "Lassen Sie mich in Outlook nach zugehörigen E-Mails suchen",
        "en": "Let me look in Outlook for related mails",
    },
    "answers_one": {
        "de": "Beantworten Sie 1 kurze Frage rechts",
        "en": "Answer 1 quick question on the right",
    },
    "answers_many": {
        "de": "Beantworten Sie {n} kurze Fragen rechts",
        "en": "Answer {n} quick questions on the right",
    },
}

# Summary sentences. The card shows 2-3 of them.
SUMMARY = {
    "clear_all": {
        "de": "Thema, Gremium und Termin sind klar.",
        "en": "Topic, committee and date are clear.",
    },
    "clear_some": {
        "de": "Verstanden: {have}. Noch offen: {missing}.",
        "en": "Understood: {have}. Still open: {missing}.",
    },
    "clear_none": {
        "de": "Ich weiß noch nicht, worum es geht: Thema, Gremium und Termin fehlen.",
        "en": "I do not know yet what this is about: topic, committee and date are missing.",
    },
    "material_none": {
        "de": "Noch kein Material hinzugefügt.",
        "en": "No material added yet.",
    },
    "material_one": {
        "de": "1 Dokument oder Link liegt vor{src}.",
        "en": "1 document or link is in{src}.",
    },
    "material_many": {
        "de": "{n} Dokumente und Links liegen vor{src}.",
        "en": "{n} documents and links are in{src}.",
    },
    "material_src": {
        "de": ", {c} Quellen werden durchsucht",
        "en": ", {c} sources will be searched",
    },
    "material_src_one": {
        "de": ", 1 Quelle wird durchsucht",
        "en": ", 1 source will be searched",
    },
    "material_reading": {
        "de": "{n} Dokumente und Links liegen vor, weitere werden noch gelesen.",
        "en": "{n} documents and links are in, more are still being read.",
    },
    "next": {
        "de": "Als Nächstes hilft am meisten: {hint}.",
        "en": "What helps most next: {hint}.",
    },
    "ready": {
        "de": "Sie können jederzeit starten. Mehr Input macht die Analyse präziser.",
        "en": "You can start at any time. More input makes the analysis sharper.",
    },
}

PARTS = {
    "topic": {"de": "Thema", "en": "topic"},
    "committee": {"de": "Gremium", "en": "committee"},
    "date": {"de": "Termin", "en": "date"},
}

QUESTIONS = {
    "decision": {
        "text": {"de": "Was benötigen Sie vom Gremium?", "en": "What do you need from the committee?"},
        "options": [
            ("approve", {"de": "Eine Option genehmigen", "en": "Approve an option"}),
            ("info", {"de": "Zur Information", "en": "For information"}),
            ("budget", {"de": "Budget freigeben", "en": "Release budget"}),
            ("postpone", {"de": "Verschieben", "en": "Postpone"}),
        ],
    },
    "favourite": {
        "text": {"de": "Favorisieren Sie bereits eine Option?", "en": "Do you already favour an option?"},
        "options": [
            ("yes", {"de": "Ja, ich habe einen Favoriten", "en": "Yes, I have a favourite"}),
            ("compare", {"de": "Noch nicht, erst vergleichen", "en": "Not yet, compare first"}),
        ],
    },
    "precedent": {
        "text": {
            "de": "Soll dies mit einem früheren Beschluss konsistent bleiben?",
            "en": "Should this stay consistent with an earlier decision?",
        },
        "text_file": {
            "de": "Ich habe „{name}“ gefunden. Soll dies mit dessen Beschlüssen konsistent bleiben?",
            "en": "I found “{name}”. Should this stay consistent with its decisions?",
        },
        "text_mention": {
            "de": "Sie erwähnen eine frühere Sitzung. Soll dies mit deren Beschlüssen konsistent bleiben?",
            "en": "You mention an earlier meeting. Should this stay consistent with its decisions?",
        },
        "options": [
            ("align", {"de": "Ja, daran ausrichten", "en": "Yes, align with it"}),
            ("fresh", {"de": "Nein, neu beginnen", "en": "No, start fresh"}),
        ],
    },
    "time": {
        "text": {
            "de": "Wie viel Zeit haben Sie im Gremium?",
            "en": "How much time will you have in the committee?",
        },
        "options": [
            ("t5", {"de": "5 Minuten", "en": "5 minutes"}),
            ("t10", {"de": "10 Minuten", "en": "10 minutes"}),
            ("t20", {"de": "20 Minuten oder mehr", "en": "20 minutes or more"}),
        ],
    },
}
