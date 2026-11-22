"""The 12 pipeline agents: rules versions, model path with guard rails, and the HTTP envelope."""
from fastapi.testclient import TestClient

from app.agents.core import AgentRunner
from app.agents.evidence_extractor import Chunk, EvidenceExtractor, EvidenceExtractorInput
from app.agents.interviewer import Interviewer, InterviewerInput, InterviewSection
from app.agents.red_team import DraftSection, RedTeam, RedTeamInput
from app.agents.registry import build_registry
from app.agents.section_analyst import AnalystSection, CalcResult, Claim, EvidenceRef, SectionAnalyst, SectionAnalystInput
from app.agents.slide_writer import SlideSection, SlideWriter, SlideWriterInput
from app.agents.source_planner import PlanSection
from app.agents.verifier import Verifier, VerifierInput
from app.config import Settings
from app.llm import LlmError
from app.main import create_app

SECS = [PlanSection(key="options", title="Optionen und Kosten", required_inputs=["Die Kosten je Option"]),
        PlanSection(key="risks", title="Risiken", required_inputs=["Die wichtigsten Risiken"])]
EV = [EvidenceRef(id="e1", statement="Option A kostet 12 Mio € über 24 Monate.", quote="Option A kostet 12 Mio € über 24 Monate.", value=12, unit="M€"),
      EvidenceRef(id="e2", statement="Option B kostet 15,5 Mio €.", quote="Option B kostet 15,5 Mio €.", value=15.5, unit="M€")]


class Scripted:
    """Model double: returns the queued answers (dict) or raises (Exception)."""
    model = "fake-deployment"

    def __init__(self, *answers):
        self.answers, self.calls, self.last_usage = list(answers), [], {"prompt_tokens": 5, "completion_tokens": 3}

    def complete_json(self, system, user, **kw):
        self.calls.append((system, user, kw))
        a = self.answers.pop(0)
        if isinstance(a, Exception):
            raise a
        return a


def test_registry_has_twelve_agents_with_unique_ids():
    reg = build_registry()
    assert len(reg) == 12 and set(reg) == {
        "template-analyst", "interviewer", "source-planner", "source-screener", "web-researcher", "evidence-extractor",
        "asset-curator", "section-analyst", "verifier", "red-team", "slide-writer", "feedback-interpreter"}
    for a in reg.values():
        assert "JSON Schema" in a.system_prompt() and a.id in a.info()["endpoint"]


def test_evidence_quote_must_occur_in_the_chunk():
    chunk = Chunk(locator="S. 3", text="Option A kostet 12 Mio € über 24 Monate. Option B kostet 15,5 Mio €.")
    model = {"items": [
        {"section_key": "options", "kind": "number", "statement": "A kostet 12 Mio €", "quote": "Option A kostet 12 Mio € über 24 Monate.", "locator": "S. 3", "value": 12, "unit": "M€"},
        {"section_key": "options", "kind": "number", "statement": "A kostet 9 Mio €", "quote": "Option A kostet 9 Mio €", "locator": "S. 3", "value": 9, "unit": "M€"},  # invented quote
        {"section_key": "nope", "kind": "fact", "statement": "x", "quote": "Option B kostet 15,5 Mio €.", "locator": "S. 3"},  # unknown section
        {"section_key": "options", "kind": "number", "statement": "B kostet 20 Mio €", "quote": "Option B kostet 15,5 Mio €.", "locator": "S. 9", "value": 20, "unit": "M€"},  # wrong locator, number not in quote
    ]}
    res = AgentRunner(Scripted(model)).run(EvidenceExtractor(), EvidenceExtractorInput(sections=SECS, document_id="d", chunks=[chunk]))
    assert res.mode == "llm"
    items = res.output.items
    assert [i.statement for i in items] == ["A kostet 12 Mio €", "B kostet 20 Mio €"]
    assert items[1].locator == "S. 3" and items[1].value is None  # locator repaired, unsupported figure removed
    assert res.output.dropped == 2 and res.usage["prompt_tokens"] == 5


def test_invalid_answer_is_repaired_once_then_rules_take_over():
    inp = InterviewerInput(sections=[InterviewSection(key="a", title="A", required_inputs=["Kosten"])], user_text="Die Kosten liegen bei 5 Mio €.")
    fake = Scripted({"statements": "not a list"}, {"statements": "still not"})
    res = AgentRunner(fake).run(Interviewer(), inp)
    assert res.mode == "rules" and "model not used" in (res.note or "") and len(fake.calls) == 2
    assert "Fehler" not in res.output.model_dump_json()
    ok = Scripted({"statements": "bad"}, {"statements": [], "coverage": [], "done": False})
    assert AgentRunner(ok).run(Interviewer(), inp).mode == "llm"


def test_model_failure_falls_back_and_cools_down():
    fake = Scripted(LlmError("boom"))
    runner = AgentRunner(fake)
    inp = InterviewerInput(sections=[InterviewSection(key="a", title="A", required_inputs=["Kosten"])])
    assert runner.run(Interviewer(), inp).mode == "rules"
    assert runner.run(Interviewer(), inp).mode == "rules" and len(fake.calls) == 1  # no second call during the cooldown


def test_interviewer_stops_when_covered_or_user_done_and_never_invents_keys():
    secs = [InterviewSection(key="options", title="Optionen", required_inputs=["Die Kosten je Option"])]
    r = AgentRunner(None)
    out = r.run(Interviewer(), InterviewerInput(sections=secs, user_text="Die Kosten je Option sind 12 Mio € für A und 15 Mio € für B.")).output
    assert out.done and out.done_reason == "all_covered" and out.next_question is None
    out = r.run(Interviewer(), InterviewerInput(sections=secs, user_done=True)).output
    assert out.done_reason == "user_done" and out.open_points
    model = {"statements": [], "coverage": [{"section_key": "ghost", "required_input": "x", "covered": True}], "next_question": {"text": "Was kostet es?", "section_key": "ghost"}}
    out = AgentRunner(Scripted(model)).run(Interviewer(), InterviewerInput(sections=secs)).output
    assert [(c.section_key, c.covered) for c in out.coverage] == [("options", False)] and out.next_question.section_key is None


def test_analyst_drops_claims_without_valid_evidence():
    sec = AnalystSection(key="options", title="Optionen")
    model = {"headline": "A ist günstiger", "claims": [
        {"id": "k1", "text": "Option A kostet 12 Mio €.", "evidence_ids": ["e1"]},
        {"id": "k2", "text": "Option C kostet 3 Mio €.", "evidence_ids": ["e99"]},
        {"id": "k3", "text": "Ohne Beleg."}], "charts": [{"id": "ch", "title": "t", "labels": ["A"], "values": [12], "evidence_ids": ["e1"]}, {"id": "bad", "title": "t", "labels": ["A", "B"], "values": [1], "evidence_ids": ["e1"]}]}
    out = AgentRunner(Scripted(model)).run(SectionAnalyst(), SectionAnalystInput(section=sec, evidence=EV)).output
    assert [c.id for c in out.claims] == ["k1"] and [c.id for c in out.charts] == ["ch"]


def test_analyst_plan_only_accepts_numeric_evidence():
    sec = AnalystSection(key="options", title="Optionen")
    ev = EV + [EvidenceRef(id="e3", statement="Es gibt zwei Lieferanten.")]
    model = {"calculations": [{"id": "c1", "label": "Summe", "formula": "a+b", "variables": {"a": "e1", "b": "e2"}},
                              {"id": "c2", "label": "Falsch", "formula": "a+b", "variables": {"a": "e1", "b": "e3"}}]}
    out = AgentRunner(Scripted(model)).run(SectionAnalyst(), SectionAnalystInput(mode="plan", section=sec, evidence=ev)).output
    assert [c.id for c in out.calculations] == ["c1"]


def test_verifier_rules_catch_a_wrong_number_and_override_a_lenient_model():
    calc = [CalcResult(id="c1", label="Summe", formula="a+b", value=27.5, unit="M€")]
    claims = [Claim(id="k1", text="Option A kostet 12 Mio € über 24 Monate.", evidence_ids=["e1"]),
              Claim(id="k2", text="Option A kostet 14 Mio €.", evidence_ids=["e1"]),
              Claim(id="k3", text="Die Summe beträgt 27,5 Mio €.", calc_ids=["c1"]),
              Claim(id="k4", text="Kein Beleg.")]
    inp = VerifierInput(section_key="options", claims=claims, evidence=EV, calculations=calc)
    checks = {c.claim_id: c for c in AgentRunner(None).run(Verifier(), inp).output.checks}
    assert checks["k1"].verdict == "supported" and checks["k3"].verdict == "supported"
    assert checks["k2"].severity == "blocker" and checks["k4"].severity == "blocker"
    lenient = {"checks": [{"claim_id": "k1", "verdict": "supported"}, {"claim_id": "k2", "verdict": "supported"}]}  # skips k3, k4
    got = {c.claim_id: c for c in AgentRunner(Scripted(lenient)).run(Verifier(), inp).output.checks}
    assert set(got) == {"k1", "k2", "k3", "k4"} and got["k2"].verdict == "unsupported" and got["k2"].severity == "blocker"


def test_red_team_flags_unverified_sections_and_cross_section_conflicts():
    a = DraftSection(key="options", title="Optionen", claims=[Claim(id="k1", text="Option A kostet 12 Mio €.", evidence_ids=["e1"])])
    b = DraftSection(key="summary", title="Zusammenfassung", claims=[Claim(id="k1", text="Option A kostet 14 Mio €.", evidence_ids=["e1"])], verified=False)
    out = AgentRunner(None).run(RedTeam(), RedTeamInput(sections=[a, b], decision_requested="Freigabe")).output
    kinds = {(c.kind, c.severity) for c in out.challenges}
    assert ("inconsistency", "warning") in kinds and ("gap", "blocker") in kinds
    # a model that forgets the unverified section does not get it past the red team
    clean = AgentRunner(Scripted({"challenges": [], "verdict": "ok"})).run(RedTeam(), RedTeamInput(sections=[b])).output
    assert any(c.severity == "blocker" for c in clean.challenges)


def test_slide_writer_never_keeps_a_bullet_without_an_approved_claim():
    sec = SlideSection(key="options", title="Optionen", headline="A ist günstiger", claims=[Claim(id="k1", text="Option A kostet 12 Mio €.", evidence_ids=["e1"])])
    model = {"slides": [{"title": "A ist günstiger", "bullets": [{"text": "Option A kostet 12 Mio €.", "claim_ids": ["k1"]}, {"text": "Erfundene Aussage", "claim_ids": ["k7"]}, {"text": "Ohne Quelle", "claim_ids": []}], "chart_id": "nope"}]}
    out = AgentRunner(Scripted(model)).run(SlideWriter(), SlideWriterInput(section=sec)).output
    assert [b.text for b in out.slides[0].bullets] == ["Option A kostet 12 Mio €."] and out.slides[0].chart_id is None


def test_http_envelope_and_validation():
    client = TestClient(create_app(Settings(agent_mode="rules")))
    agents = client.get("/v1/agents").json()
    assert {a["id"] for a in agents if a["status"] == "available"} >= {"brief", "verifier", "red-team", "feedback-interpreter"}
    assert len([a for a in agents if a["id"] != "brief"]) == 12
    r = client.post("/v1/agents/template-analyst/run", json={"lang": "en", "topic": "x"})
    body = r.json()
    assert r.status_code == 200 and body["mode"] == "rules" and len(body["output"]["sections"]) == 7
    assert client.post("/v1/agents/verifier/run", json={}).status_code == 422
    assert client.post("/v1/agents/ghost/run", json={}).status_code == 404
    assert "properties" in client.get("/v1/agents/verifier/schema").json()["output"]
