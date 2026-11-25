"""End-to-end run on this machine: starts agents (rules mode) and backend, drives the whole workflow over HTTP.

    python e2e/run_e2e.py            # start both services on free ports, run, stop
    python e2e/run_e2e.py --keep     # leave the generated decks in e2e/out/
    python e2e/run_e2e.py --url http://localhost:8001   # demo against services you already started (creates a report you can open)

It checks the two steps (brief, draft), the guard rails (a wrong number is caught and kept out of the slides), Ask AI with undo, and the export.
"""
from __future__ import annotations

import io
import os
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).parent))
from make_samples import write_all  # noqa: E402


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_up(url: str, timeout: float = 30) -> None:
    t = time.time()
    while time.time() - t < timeout:
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            time.sleep(0.3)
    raise RuntimeError(f"{url} did not start")


def step(msg: str) -> None:
    print(f"\n== {msg}")


def check(cond: bool, msg: str) -> None:
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        raise AssertionError(msg)


def main(keep: bool = False, url: str | None = None) -> int:
    tmp = Path(tempfile.mkdtemp(prefix="coe4-e2e-"))
    env = {**os.environ, "PYTHONUNBUFFERED": "1"}
    procs = []
    try:
        if url:
            base_url = url.rstrip("/")
            wait_up(base_url + "/health")
        else:
            ap, bp = free_port(), free_port()
            procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(ap), "--log-level", "warning"], cwd=ROOT / "agents", env={**env, "AGENT_MODE": "rules"}))
            procs.append(subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(bp), "--log-level", "warning"], cwd=ROOT / "backend",
                                          env={**env, "AGENTS_URL": f"http://127.0.0.1:{ap}", "DATA_DIR": str(tmp / "data")}))
            wait_up(f"http://127.0.0.1:{ap}/health")
            base_url = f"http://127.0.0.1:{bp}"
            wait_up(base_url + "/health")
        c = httpx.Client(base_url=base_url, timeout=300 if url else 60)
        samples = write_all(tmp / "samples")

        def job(rid: str, jid: str, timeout=120) -> dict:
            t = time.time()
            while time.time() - t < timeout:
                j = c.get(f"/api/v1/reports/{rid}/jobs/{jid}").json()
                if j["status"] in ("done", "failed"):
                    return j
                time.sleep(0.4)
            raise TimeoutError(jid)

        step("create report, brief, files")
        rid = c.post("/api/v1/reports", json={"title": "Dual-Sourcing Batteriezellen", "committee_id": "fakom"}).json()["id"]
        r = c.put(f"/api/v1/reports/{rid}/case", json={"topic": "Dual Sourcing für Hochvolt-Batteriezellen", "decision_requested": "Freigabe von Option A", "lang": "de"})
        check(r.status_code == 200 and r.json()["state"] == "SETUP", "case saved, state SETUP")
        for name, role in [("template.pptx", "template"), ("Angebote_Batteriezellen.docx", "source"), ("Kostenmodell_Dual_Sourcing.xlsx", "source"),
                           ("Risiken_Dual_Sourcing.md", "source"), ("Projektplan_Dual_Sourcing.txt", "source"), ("Urlaubsplanung.txt", "source")]:
            r = c.post(f"/api/v1/reports/{rid}/files", files={"file": (name, samples[name].read_bytes())}, data={"role": role})
            check(r.status_code == 201, f"uploaded {name}")
        check(c.post(f"/api/v1/reports/{rid}/files", files={"file": ("x.exe", b"MZ")}, data={"role": "source"}).status_code == 422, "unsupported file type refused")

        step("brief: outline + interview, then the draft is built")
        check(c.post(f"/api/v1/reports/{rid}/outline/approve").status_code == 409, "cannot approve before the outline exists")
        o = c.post(f"/api/v1/reports/{rid}/outline/propose").json()
        keys = [s["key"] for s in o["sections"]]
        check(len(keys) == 6 and "management-summary" in keys, f"outline from template: {keys}")
        t0 = c.post(f"/api/v1/reports/{rid}/interview/turn", json={}).json()
        check(bool(t0["next_question"]), f"first question: {t0['next_question']['text'][:70]}")
        t1 = c.post(f"/api/v1/reports/{rid}/interview/turn", json={"text": "Wir empfehlen Option A. Das Gremium soll die Freigabe von 12 Mio € beschließen."}).json()
        check(len(t1["statements"]) >= 1, "statements captured from the interview")
        sections = [{**s, "included": s["key"] != "management-summary" or True} for s in o["sections"]]
        c.put(f"/api/v1/reports/{rid}/outline", json=sections)
        j = c.post(f"/api/v1/reports/{rid}/outline/approve").json()["job_id"]
        res = job(rid, j)
        check(res["status"] == "done", f"research + analysis job done ({res.get('error')})")
        case = c.get(f"/api/v1/reports/{rid}/case").json()
        check(case["state"] == "DECK_REVIEW", f"the draft is built in one go, state DECK_REVIEW, counts {case['counts']}")
        srcs = c.get(f"/api/v1/reports/{rid}/sources").json()
        check(any(s["status"] == "rejected" for s in srcs) or all(s["status"] == "parsed" for s in srcs), "sources screened")
        check(case["counts"]["evidence"] >= 8, "evidence extracted")

        step("the draft: evidence, edits, Ask AI, download")
        f = c.get(f"/api/v1/reports/{rid}/findings").json()
        opt = next(s for s in f["sections"] if s["key"].startswith("optionen"))
        check(len(opt["claims"]) >= 2, f"options section has {len(opt['claims'])} claims")
        check(all(cl["evidence"] or cl["calculations"] for cl in opt["claims"]), "every claim has evidence or a calculation")
        ev_quote = next(e for cl in opt["claims"] for e in cl["evidence"] if e["quote"])
        check(bool(ev_quote["locator"] and ev_quote["source"]), f"traceable: '{ev_quote['quote'][:50]}' <- {ev_quote['source']}, {ev_quote['locator']}")
        check(c.post(f"/api/v1/reports/{rid}/findings/approve").status_code == 404 and c.post(f"/api/v1/reports/{rid}/deck/finalize").status_code == 404, "no sign-off steps exist")
        # an edit with a wrong number is caught, kept out of the slides and listed; it never blocks the download
        victim = opt["claims"][0]
        r = c.patch(f"/api/v1/reports/{rid}/claims/{victim['id']}", json={"text": "Option A kostet 99 Mio €."}).json()
        check(r["status"] == "flagged" and r["verdict"] in ("unsupported", "contradicted"), f"edited claim with a wrong number is flagged ({r['verdict']})")
        d = c.get(f"/api/v1/reports/{rid}/deck").json()
        check(any(a["kind"] == "claim" and a["id"] == victim["id"] for a in d["attention"]), "the left-out claim is listed under attention")
        check(len(d["slides"]) >= 4 and d["has_file"] and d["export"]["slides"] <= len(d["slides"]), f"{len(d['slides'])} slides in the draft, {d['export']['slides']} pages in the file")
        check(all(b["claim_ids"] for s in d["slides"] for b in s["bullets"]), "every bullet is tied to a claim")
        sl = next(s for s in d["slides"] if s["bullets"])
        r = c.patch(f"/api/v1/reports/{rid}/deck/slides/{sl['id']}", json={"bullets": [sl["bullets"][0]["text"], "Neue Zahl 777 Mio €."]}).json()
        check(len(r["warnings"]) == 1, f"a number outside the verified claims is warned about: {r['warnings']}")
        a1 = c.post(f"/api/v1/reports/{rid}/deck/ask", json={"text": "Bei den Risiken ist die Aussage falsch, bitte neu berechnen und korrigieren.", "scope": "section", "section_key": next(x["key"] for x in f["sections"] if x["key"].startswith("risiken"))})
        check(a1.status_code in (200, 202) and a1.json()["mode"] == "job", f"Ask AI on a section runs as a job ({a1.text[:100]})")
        check(job(rid, a1.json()["job_id"])["status"] == "done", "the section was written again in place")
        case = c.get(f"/api/v1/reports/{rid}/case").json()
        check(case["version"] == "v1" and case["state"] == "DECK_REVIEW", f"still one version, state {case['state']}")
        check(c.post(f"/api/v1/reports/{rid}/deck/ask/undo").status_code == 200, "the last AI change can be undone")
        pptx = c.get(f"/api/v1/reports/{rid}/deck/download")
        check(pptx.status_code == 200 and pptx.content[:2] == b"PK", f"pptx downloaded ({len(pptx.content)} bytes)")
        from pptx import Presentation
        prs = Presentation(io.BytesIO(pptx.content))
        check(len(prs.slides) == c.get(f"/api/v1/reports/{rid}/deck").json()["export"]["slides"], f"the file has the announced {len(prs.slides)} pages (short sections share a page)")
        text = "\n".join(sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame)
        check("12 Mio" in text and "Quellen" in text, "deck contains the verified figure and a sources slide")
        check(any(sh.has_chart for s in prs.slides for sh in s.shapes if getattr(sh, "has_chart", False)), "deck contains a native chart built from ledger numbers")
        if keep:
            out = ROOT / "e2e" / "out"
            out.mkdir(exist_ok=True)
            (out / "deck.pptx").write_bytes(pptx.content)

        step("audit trail")
        runs = c.get(f"/api/v1/reports/{rid}/agent-runs").json()
        ids = {r["agent"] for r in runs}
        need = {"template-analyst", "interviewer", "evidence-extractor", "source-planner", "section-analyst", "verifier", "red-team", "storyline-architect", "slide-writer", "feedback-interpreter"}
        check(need <= ids, f"{len(ids)} agents were called, including every one of the main chain: {sorted(ids)}")
        modes = sorted({r["mode"] for r in runs})
        print(f"  info agent modes used: {modes}" + ("  (llm = your Foundry model answered; rules = the built-in fallback)" if url else ""))
        if not url:
            check(modes == ["rules"], "all runs in rules mode")
        ev = c.get(f"/api/v1/reports/{rid}/events").json()
        check({"outline_approved", "deck_exported"} <= {e["kind"] for e in ev}, f"{len(ev)} events recorded")
        print(f"\nALL CHECKS PASSED ({len(runs)} agent calls, {len(ev)} events)" + (f". Open {base_url}/docs and look at /api/v1/reports/{rid}/agent-runs" if url else f", database {tmp / 'data' / 'coe4.db'}"))
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"\nE2E FAILED: {e.__class__.__name__}: {e}")
        return 1
    finally:
        for p in procs:
            p.terminate()
        for p in procs:
            try:
                p.wait(5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    u = sys.argv[sys.argv.index("--url") + 1] if "--url" in sys.argv else None
    sys.exit(main("--keep" in sys.argv, u))
