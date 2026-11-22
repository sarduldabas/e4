from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.agents.brief_agent import BriefAgent
from app.config import Settings
from app.main import create_app
from app.schemas import BriefAssessRequest, BriefFile

TODAY = date(2026, 11, 22)
agent = BriefAgent(today=TODAY)

SAMPLE_EN = (
    "I need to prepare the FAKOM report for 3 December on our dual-sourcing strategy for high-voltage battery cells. "
    "Today everything comes from Supplier A, and the guideline wants two qualified sources before start of production. "
    "I am comparing a single source, a 60/40 split with Supplier B, and a version with a regional plant for Supplier B. "
    "I think the 60/40 split is the right one, but the committee will want to see cost, risk and timeline. "
    "Last time they asked for a sensitivity analysis, so please include that."
)
SAMPLE_DE = (
    "Ich muss den FAKOM-Bericht für den 3. Dezember zu unserer Dual-Sourcing-Strategie für Hochvolt-Batteriezellen vorbereiten. "
    "Heute kommt alles von Lieferant A. Ich halte die 60/40-Aufteilung für richtig. Beim letzten Mal wurde eine Sensitivitätsanalyse gefordert."
)
FILES = [BriefFile(name=n) for n in [
    "Supplier_A_Offer_v3.pptx", "Supplier_B_Proposal.pdf", "Cost_model_Q3.xlsx",
    "RE: Cell qualification timeline", "Teams export: Sourcing sync", "FAKOM_Report_2025-Q2.pptx"]]
CONNECTORS = {"confluence": True, "jira": True, "wiki": True, "web": True, "outlook": False, "sharepoint": False, "teams": False}


def req(**kw):
    return BriefAssessRequest(**kw)


def test_empty_brief_is_getting_started_and_asks_for_topic():
    a = agent.assess(req(lang="en"))
    assert a.strength.score == 0
    assert a.strength.label_key == "getting_started"
    assert a.strength.missing[0] == "topic"
    assert len(a.strength.hints) == 3
    assert not a.can_start
    assert len(a.questions) == 3  # decision, favourite, precedent


def test_sample_brief_en_matches_front_end_formula():
    # Same formula as the prototype's local scoring (briefStrength in workspace.js): 15+10+8 + 17 (80+ words) + 28 (6 items) + 4.8 (4 of 5 sources) + 16 = 98.8
    a = agent.assess(req(lang="en", text=SAMPLE_EN, files=FILES, connectors=CONNECTORS,
                         answers={"q1": "approve", "q2": "yes", "q3": "align"}))
    assert a.understood.committee == "FAKOM"
    assert a.understood.date == "03.12.2026"
    assert a.understood.topic.lower().startswith("dual-sourcing strategy")
    assert a.strength.score == 99
    assert a.strength.label_key == "excellent_brief"
    assert a.can_start


def test_text_that_already_answers_a_question_skips_it():
    a = agent.assess(req(lang="en", text=SAMPLE_EN))
    ids = [q.id for q in a.questions]
    assert "q2" not in ids  # "I think the 60/40 split is the right one" -> favourite is clear
    assert "favourite" in a.already_clear
    assert len(ids) == 3


def test_answered_questions_never_disappear():
    a = agent.assess(req(lang="en", text=SAMPLE_EN, answers={"q2": "yes"}))
    assert "q2" in [q.id for q in a.questions]
    assert next(q for q in a.questions if q.id == "q2").answer == "yes"


def test_precedent_file_is_named_in_the_question():
    a = agent.assess(req(lang="de", files=FILES))
    q3 = next(q for q in a.questions if q.id == "q3")
    assert "FAKOM_Report_2025-Q2.pptx" in q3.text


def test_german_output_and_german_text_detection():
    a = agent.assess(req(lang="de", text=SAMPLE_DE, files=FILES, connectors=CONNECTORS))
    assert a.understood.committee == "FAKOM"
    assert a.understood.date == "03.12.2026"
    assert a.strength.label in {"Gute Basis", "Starkes Briefing", "Ausgezeichnetes Briefing", "Am Anfang"}
    assert all("the" not in h.split() for h in a.strength.hints)
    assert any("Frage" in q.text or "?" in q.text for q in a.questions)


def test_overrides_win_over_detection():
    a = agent.assess(req(lang="en", text=SAMPLE_EN, overrides={"committee": "Investment Committee", "date": "14.01.2027"}))
    assert a.understood.committee == "Investment Committee"
    assert a.understood.date == "14.01.2027"


def test_files_still_reading_do_not_count_as_material():
    ready = agent.assess(req(lang="en", files=[BriefFile(name="a.pdf", status="ready")])).strength.score
    reading = agent.assess(req(lang="en", files=[BriefFile(name="a.pdf", status="reading")])).strength.score
    assert reading < ready


def test_summary_is_two_to_three_sentences_and_hints_max_three():
    a = agent.assess(req(lang="en", text="Short note about the FAKOM report."))
    assert 2 <= a.strength.summary.count(". ") + 1 <= 4
    assert len(a.strength.hints) <= 3


def test_date_rolls_to_next_year_when_already_past():
    a = BriefAgent(today=date(2026, 12, 20)).assess(req(lang="en", text="Report for 3 December on supply planning for cells"))
    assert a.understood.date == "03.12.2027"


@pytest.mark.parametrize("lang", ["de", "en"])
def test_http_endpoint(lang):
    c = TestClient(create_app(Settings(agent_mode="rules")))
    r = c.post("/v1/brief/assess", json={"lang": lang, "text": "FAKOM on 3 December, dual sourcing for battery cells"})
    assert r.status_code == 200
    body = r.json()
    assert body["lang"] == lang and 0 <= body["strength"]["score"] <= 100
    assert c.get("/health").json()["status"] == "ok"
    assert any(a["id"] == "brief" and a["status"] == "available" for a in c.get("/v1/agents").json())
