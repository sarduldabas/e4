"""The workflow on the database, with the real agents service (rules mode)."""
import io
import sys
from pathlib import Path

import pytest
from pptx import Presentation

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "e2e"))
from make_samples import write_all  # noqa: E402

from app.models import AgentRun, Claim, Event, Evidence, Report  # noqa: E402


@pytest.fixture()
def case(make_client, tmp_path):
    c = make_client()
    files = write_all(tmp_path / "samples")
    rid = c.post("/api/v1/reports", json={"title": "Dual Sourcing", "committee_id": "fakom"}).json()["id"]
    c.put(f"/api/v1/reports/{rid}/case", json={"topic": "Dual Sourcing für Hochvolt-Batteriezellen", "decision_requested": "Freigabe von Option A"})
    for name, role in [("template.pptx", "template"), ("Angebote_Batteriezellen.docx", "source"), ("Kostenmodell_Dual_Sourcing.xlsx", "source"), ("Risiken_Dual_Sourcing.md", "source"),
                       ("Projektplan_Dual_Sourcing.txt", "source")]:
        assert c.post(f"/api/v1/reports/{rid}/files", files={"file": (name, files[name].read_bytes())}, data={"role": role}).status_code == 201
    return c, rid, f"/api/v1/reports/{rid}"


def research(c, base):
    c.post(f"{base}/outline/propose")
    j = c.post(f"{base}/outline/approve")
    assert j.status_code == 202, j.text
    return c.get(f"{base}/jobs/{j.json()['job_id']}").json()


def test_steps_are_refused_in_the_wrong_state(case):
    c, rid, base = case
    assert c.post(f"{base}/findings/approve").status_code == 409
    assert c.get(f"{base}/deck/download").status_code == 404
    assert c.post(f"{base}/deck/finalize").status_code == 409
    assert c.post(f"{base}/outline/approve").status_code == 409  # no outline yet
    assert c.patch(f"{base}/claims/k-nope", json={"status": "approved"}).status_code == 409
    c.post(f"{base}/outline/propose")
    assert c.put(f"{base}/case", json={"topic": "x"}).status_code == 200  # still editable before research
    assert c.get(f"{base}/case").json()["state"] == "OUTLINE_REVIEW"


def test_outline_edits_are_kept_and_removed_sections_stay_out(case):
    c, rid, base = case
    secs = c.post(f"{base}/outline/propose").json()["sections"]
    edited = [{**s, "title": "Kosten der Optionen"} if s["key"] == "optionen-und-kosten" else s for s in secs if s["key"] != "zeitplan-und-meilensteine"]
    edited.append({"title": "Anhang Lieferantenbewertung", "purpose": "Details"})
    out = c.put(f"{base}/outline", json=edited).json()
    by = {s["key"]: s for s in out}
    assert by["optionen-und-kosten"]["title"] == "Kosten der Optionen" and by["optionen-und-kosten"]["origin"] == "user"
    assert by["zeitplan-und-meilensteine"]["included"] is False and by["anhang-lieferantenbewertung"]["origin"] == "user"
    again = c.post(f"{base}/outline/propose").json()["sections"]  # a new proposal must not undo the user's edits
    assert {s["key"]: s for s in again}["optionen-und-kosten"]["title"] == "Kosten der Optionen"


def test_research_builds_a_traceable_ledger(case):
    c, rid, base = case
    assert research(c, base)["status"] == "done"
    f = c.get(f"{base}/findings").json()
    claims = [cl for s in f["sections"] for cl in s["claims"]]
    assert claims and all(cl["evidence"] or cl["calculations"] for cl in claims)
    for cl in claims:
        for e in cl["evidence"]:
            assert e["locator"] and e["source"] and e["quote"]
    with c.app.state.db.session() as s:
        # every document quote really occurs in the parsed source text
        import json
        from app.models import Source
        parsed = {x.id: " ".join(ch["text"] for ch in json.loads(c.app.state.ctx.store.get(x.parsed_key))["chunks"]) for x in s.query(Source).filter(Source.parsed_key.isnot(None)).all()}
        for e in s.query(Evidence).filter_by(report_id=rid, origin="document").all():
            assert " ".join(e.quote.split()).lower() in " ".join(parsed[e.source_id].split()).lower()
        assert s.query(AgentRun).filter_by(report_id=rid, status="error").count() == 0
        assert s.query(Event).filter_by(report_id=rid, kind="outline_approved").count() == 1


def test_calculations_are_code_and_charts_use_ledger_numbers(case):
    c, rid, base = case
    research(c, base)
    f = c.get(f"{base}/findings").json()
    opt = next(s for s in f["sections"] if s["key"] == "optionen-und-kosten")
    calc = [k for cl in opt["claims"] for k in cl["calculations"]]
    assert calc and abs(calc[0]["value"] - 6.0) < 1e-9  # 18 - 12
    assert opt["charts"] and sorted(opt["charts"][0]["values"]) == [12.0, 15.5, 18.0]


def test_edited_claim_is_reverified_and_a_blocker_stops_generation(case):
    c, rid, base = case
    research(c, base)
    f = c.get(f"{base}/findings").json()
    claim = next(cl for s in f["sections"] if s["key"] == "optionen-und-kosten" for cl in s["claims"] if "Option A" in cl["text"])
    r = c.patch(f"{base}/claims/{claim['id']}", json={"text": "Option A kostet 99 Mio €."}).json()
    assert r["status"] == "flagged" and r["reverified"]["severity"] == "blocker"
    blocked = c.post(f"{base}/findings/approve")
    assert blocked.status_code == 409 and blocked.json()["items"]
    # fixing the claim back to what the source says lifts the verifier flag
    ok = c.patch(f"{base}/claims/{claim['id']}", json={"text": "Option A kostet 12 Mio € über 24 Monate."}).json()
    assert ok["status"] == "verified"
    flags = [x for s in c.get(f"{base}/findings").json()["sections"] for x in s["flags"] if x["claim_id"] == claim["id"] and x["origin"] == "verifier"]
    assert all(x["status"] == "resolved" for x in flags if x["severity"] == "blocker")


def test_accepting_a_blocker_needs_a_reason_and_is_recorded(case):
    c, rid, base = case
    research(c, base)
    f = c.get(f"{base}/findings").json()
    claim = f["sections"][0]["claims"][0] if f["sections"][0]["claims"] else next(cl for s in f["sections"] for cl in s["claims"])
    c.patch(f"{base}/claims/{claim['id']}", json={"text": "Das Volumen beträgt 777 Stück."})
    flag = next(x for s in c.get(f"{base}/findings").json()["sections"] for x in s["flags"] if x["claim_id"] == claim["id"] and x["status"] == "open" and x["severity"] == "blocker")
    assert c.post(f"{base}/flags/{flag['id']}/resolve", json={"resolution": "accepted"}).status_code == 409
    ok = c.post(f"{base}/flags/{flag['id']}/resolve", json={"resolution": "accepted", "note": "Zahl aus Telefonat mit dem Einkauf"})
    assert ok.status_code == 200
    ev = [e for e in c.get(f"{base}/events").json() if e["kind"] == "flag_resolved"]
    assert ev and ev[-1]["payload"]["note"] == "Zahl aus Telefonat mit dem Einkauf"


def approve_all(c, base):
    f = c.get(f"{base}/findings").json()
    for fl in [x for s in f["sections"] for x in s["flags"]] + f["general_flags"]:
        if fl["severity"] == "blocker" and fl["status"] == "open":
            c.post(f"{base}/flags/{fl['id']}/resolve", json={"resolution": "dismissed", "note": "geprüft"})
    j = c.post(f"{base}/findings/approve")
    assert j.status_code == 202, j.text
    return c.get(f"{base}/jobs/{j.json()['job_id']}").json()


def test_deck_is_built_from_approved_claims_with_sources_and_native_chart(case):
    c, rid, base = case
    research(c, base)
    assert approve_all(c, base)["status"] == "done"
    d = c.get(f"{base}/deck").json()
    assert d["has_file"] and all(b["claim_ids"] for s in d["slides"] for b in s["bullets"])
    prs = Presentation(io.BytesIO(c.get(f"{base}/deck/download").content))
    assert any(getattr(sh, "has_chart", False) and sh.has_chart for s in prs.slides for sh in s.shapes)
    notes = " ".join(s.notes_slide.notes_text_frame.text for s in prs.slides if s.has_notes_slide)
    assert "Belege:" in notes
    # a user edit with a number that no verified claim contains is warned about
    sl = d["slides"][0]
    w = c.patch(f"{base}/deck/slides/{sl['id']}", json={"bullets": ["Neue Zahl 777"]}).json()
    assert w["warnings"]
    assert c.get(f"{base}/case").json()["state"] == "DECK_REVIEW"


def test_feedback_creates_v2_carries_approved_claims_and_lists_changes(case):
    c, rid, base = case
    research(c, base)
    approve_all(c, base)
    fb = c.post(f"{base}/feedback", json={"text": "Bei den Risiken ist die Aussage falsch, bitte korrigieren."}).json()
    assert fb["changes"][0]["rerun_from"] == "analysis"
    j = c.post(f"{base}/feedback/{fb['id']}/apply").json()["job_id"]
    assert c.get(f"{base}/jobs/{j}").json()["status"] == "done"
    assert c.get(f"{base}/case").json()["version"] == "v2"
    with c.app.state.db.session() as s:
        v1 = s.query(Claim).filter_by(report_id=rid, version_no=1, status="approved").count()
        carried = s.query(Claim).filter(Claim.report_id == rid, Claim.version_no == 2, Claim.carried_from.isnot(None)).count()
        assert carried and carried < v1 + 1  # unchanged sections carried forward; the re-analysed section was not copied
        assert s.get(Report, rid).version_no == 2


def test_web_researcher_runs_only_when_web_is_allowed(case):
    c, rid, base = case
    c.app.state.ctx.settings.allow_web = True

    class Stub:
        allow = True

        def fetch(self, url):
            return url, "<html><title>Marktstudie</title><p>Der Weltmarkt für Batteriezellen wächst im Jahr 2026 um 18 % bei den Kosten pro Option.</p></html>"
    c.app.state.ctx.web = Stub()
    c.put(f"{base}/case", json={"links": ["https://example.org/studie"]})
    research(c, base)
    with c.app.state.db.session() as s:
        assert s.query(AgentRun).filter_by(report_id=rid, agent_id="web-researcher").count() == 1
        web = s.query(Evidence).filter_by(report_id=rid, origin="web").all()
        assert web and "18" in web[0].quote


def test_web_is_blocked_for_internal_addresses_and_when_off():
    from app.core.connectors import WebFetcher
    with pytest.raises(PermissionError):
        WebFetcher(False).fetch("https://example.org")
    for u in ("http://localhost:8001/api", "http://192.168.1.5/x", "http://10.0.0.1/", "http://intranet.internal/"):
        with pytest.raises(PermissionError):
            WebFetcher(True).fetch(u)


def test_agents_service_down_gives_a_clear_error_and_no_state_change(make_client):
    c = make_client(url="http://127.0.0.1:9")
    rid = c.post("/api/v1/reports", json={"title": "x"}).json()["id"]
    r = c.post(f"/api/v1/reports/{rid}/outline/propose")
    assert r.status_code == 503 and "not reachable" in r.json()["detail"]
    assert c.get(f"/api/v1/reports/{rid}/case").json()["state"] == "SETUP"
    with c.app.state.db.session() as s:
        assert s.query(AgentRun).filter_by(report_id=rid, status="error").count() == 1


def test_failed_job_is_recorded_and_restart_recovers_stuck_jobs(case):
    c, rid, base = case
    # run the research with the service unreachable: the job fails and says why
    c.app.state.ctx.runner._c.close()
    from app.services.runner import AgentsRunner
    c.app.state.ctx.runner = AgentsRunner("http://127.0.0.1:9", 2, c.app.state.db)
    with c.app.state.db.session() as s:
        from app.models import OutlineSection
        s.add(OutlineSection(report_id=rid, key="a", title="A", required_inputs=["x"]))
        r = s.get(Report, rid)
        r.state = "OUTLINE_REVIEW"
    j = c.post(f"{base}/outline/approve").json()["job_id"]
    job = c.get(f"{base}/jobs/{j}").json()
    assert job["status"] == "failed" and "not reachable" in job["error"]
    from app.models import Job
    with c.app.state.db.session() as s:
        s.add(Job(report_id=rid, kind="research", status="running"))
    c.app.state.ctx.jobs.recover()
    with c.app.state.db.session() as s:
        assert s.query(Job).filter_by(report_id=rid, status="running").count() == 0


def test_deleting_a_report_removes_files_and_audit_trail(case):
    c, rid, base = case
    research(c, base)
    root = c.app.state.ctx.store.root / "reports" / rid
    assert root.exists()
    assert c.delete(f"/api/v1/reports/{rid}").status_code == 204
    assert not root.exists()
    with c.app.state.db.session() as s:
        assert s.query(AgentRun).filter_by(report_id=rid).count() == 0 and s.query(Evidence).filter_by(report_id=rid).count() == 0
