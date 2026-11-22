"""End-to-end run on this machine: starts agents (rules mode) and backend, drives the whole workflow over HTTP.

    python e2e/run_e2e.py            # start both services on free ports, run, stop
    python e2e/run_e2e.py --keep     # leave the generated decks in e2e/out/
    python e2e/run_e2e.py --url http://localhost:8001   # demo against services you already started (creates a report you can open)

It checks the three checkpoints, the guard rails (a wrong number is caught, blockers stop generation) and version 2.
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

        step("checkpoint 1: outline + interview")
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
        check(case["state"] == "FINDINGS_REVIEW", f"state FINDINGS_REVIEW, counts {case['counts']}")
        srcs = c.get(f"/api/v1/reports/{rid}/sources").json()
        check(any(s["status"] == "rejected" for s in srcs) or all(s["status"] == "parsed" for s in srcs), "sources screened")
        check(case["counts"]["evidence"] >= 8, "evidence extracted")

        step("checkpoint 2: findings")
        f = c.get(f"/api/v1/reports/{rid}/findings").json()
        opt = next(s for s in f["sections"] if s["key"].startswith("optionen"))
        check(len(opt["claims"]) >= 2, f"options section has {len(opt['claims'])} claims")
        check(all(cl["evidence"] or cl["calculations"] for cl in opt["claims"]), "every claim has evidence or a calculation")
        ev_quote = next(e for cl in opt["claims"] for e in cl["evidence"] if e["quote"])
        check(bool(ev_quote["locator"] and ev_quote["source"]), f"traceable: '{ev_quote['quote'][:50]}' <- {ev_quote['source']}, {ev_quote['locator']}")
        # an edit with a wrong number must be caught and block approval
        victim = opt["claims"][0]
        r = c.patch(f"/api/v1/reports/{rid}/claims/{victim['id']}", json={"text": "Option A kostet 99 Mio €."}).json()
        check(r["status"] == "flagged" and r["verdict"] in ("unsupported", "contradicted"), f"edited claim with a wrong number is flagged ({r['verdict']})")
        blocked = c.post(f"/api/v1/reports/{rid}/findings/approve")
        check(blocked.status_code == 409 and blocked.json()["items"], "generation blocked while a blocker flag is open")
        fl = next(x for x in c.get(f"/api/v1/reports/{rid}/findings").json()["sections"] if x["key"] == opt["key"])["flags"]
        open_b = [x for x in fl if x["severity"] == "blocker" and x["status"] == "open"]
        check(c.post(f"/api/v1/reports/{rid}/flags/{open_b[0]['id']}/resolve", json={"resolution": "accepted"}).status_code == 409, "a blocker can not be accepted without a reason")
        r = c.patch(f"/api/v1/reports/{rid}/claims/{victim['id']}", json={"status": "rejected"})
        check(r.status_code == 200, "wrong claim rejected")
        f = c.get(f"/api/v1/reports/{rid}/findings").json()
        for fl in [x for s in f["sections"] for x in s["flags"] if x["severity"] == "blocker" and x["status"] == "open"]:
            c.post(f"/api/v1/reports/{rid}/flags/{fl['id']}/resolve", json={"resolution": "dismissed", "note": "Kenne ich, ist für die Vorlage irrelevant."})
        general = [x for x in f["general_flags"] if x["severity"] == "blocker" and x["status"] == "open"]
        for fl in general:
            c.post(f"/api/v1/reports/{rid}/flags/{fl['id']}/resolve", json={"resolution": "dismissed", "note": "geprüft"})
        j = c.post(f"/api/v1/reports/{rid}/findings/approve")
        check(j.status_code == 202, f"findings approved ({j.text[:100]})")
        res = job(rid, j.json()["job_id"])
        check(res["status"] == "done", f"deck generated ({res.get('error')})")

        step("checkpoint 3: deck")
        d = c.get(f"/api/v1/reports/{rid}/deck").json()
        check(len(d["slides"]) >= 4 and d["has_file"], f"{len(d['slides'])} content slides")
        check(all(b["claim_ids"] for s in d["slides"] for b in s["bullets"]), "every bullet is tied to a claim")
        sl = d["slides"][0]
        r = c.patch(f"/api/v1/reports/{rid}/deck/slides/{sl['id']}", json={"bullets": [sl["bullets"][0]["text"], "Neue Zahl 777 Mio €."]}).json()
        check(len(r["warnings"]) == 1, f"a number outside the verified claims is warned about: {r['warnings']}")
        pptx = c.get(f"/api/v1/reports/{rid}/deck/download")
        check(pptx.status_code == 200 and pptx.content[:2] == b"PK", f"pptx downloaded ({len(pptx.content)} bytes)")
        from pptx import Presentation
        prs = Presentation(io.BytesIO(pptx.content))
        text = "\n".join(sh.text_frame.text for s in prs.slides for sh in s.shapes if sh.has_text_frame)
        check("12 Mio" in text and "Quellen" in text, "deck contains the verified figure and a sources slide")
        check(any(sh.has_chart for s in prs.slides for sh in s.shapes if getattr(sh, "has_chart", False)), "deck contains a native chart built from ledger numbers")
        if keep:
            out = ROOT / "e2e" / "out"
            out.mkdir(exist_ok=True)
            (out / "deck_v1.pptx").write_bytes(pptx.content)

        step("feedback -> version 2")
        check(c.post(f"/api/v1/reports/{rid}/feedback", json={"text": "x"}).status_code == 422, "too-short feedback refused")
        c.post(f"/api/v1/reports/{rid}/deck/finalize")
        check(c.get(f"/api/v1/reports/{rid}/case").json()["state"] == "FINAL", "deck final")
        fbk = c.post(f"/api/v1/reports/{rid}/feedback", json={"text": "Bei den Risiken ist die Aussage falsch, bitte neu berechnen und korrigieren."}).json()
        check(fbk["changes"] and fbk["changes"][0]["rerun_from"] == "analysis", f"interpreted: {fbk['changes'][0]['action']} -> {fbk['changes'][0]['rerun_from']} ({fbk['changes'][0]['section_key']})")
        j = c.post(f"/api/v1/reports/{rid}/feedback/{fbk['id']}/apply").json()["job_id"]
        res = job(rid, j)
        check(res["status"] == "done", f"version 2 job done ({res.get('error')})")
        case = c.get(f"/api/v1/reports/{rid}/case").json()
        check(case["version"] == "v2" and case["state"] == "FINDINGS_REVIEW", f"v2 awaiting approval of re-analysed section, state {case['state']}")
        f2 = c.get(f"/api/v1/reports/{rid}/findings").json()
        carried = [cl for s in f2["sections"] for cl in s["claims"] if cl["status"] == "approved"]
        check(len(carried) >= 5, f"approved claims carried forward: {len(carried)}")
        for fl in [x for s in f2["sections"] for x in s["flags"] if x["severity"] == "blocker" and x["status"] == "open"] + [x for x in f2["general_flags"] if x["severity"] == "blocker" and x["status"] == "open"]:
            c.post(f"/api/v1/reports/{rid}/flags/{fl['id']}/resolve", json={"resolution": "dismissed", "note": "geprüft"})
        j = c.post(f"/api/v1/reports/{rid}/findings/approve")
        check(j.status_code == 202, f"v2 findings approved ({j.text[:120]})")
        check(job(rid, j.json()["job_id"])["status"] == "done", "v2 deck generated")
        d2 = c.get(f"/api/v1/reports/{rid}/deck").json()
        pptx2 = c.get(f"/api/v1/reports/{rid}/deck/download").content
        t2 = "\n".join(sh.text_frame.text for s in Presentation(io.BytesIO(pptx2)).slides for sh in s.shapes if sh.has_text_frame)
        check("Änderungen gegenüber v1" in t2, "v2 deck has the 'changes since v1' slide")
        if keep:
            (ROOT / "e2e" / "out" / "deck_v2.pptx").write_bytes(pptx2)

        step("audit trail")
        runs = c.get(f"/api/v1/reports/{rid}/agent-runs").json()
        ids = {r["agent"] for r in runs}
        check(len(ids) == 11 and "web-researcher" not in ids, f"11 agents were called (the 12th, web-researcher, runs only with ALLOW_WEB=true): {sorted(ids)}")
        modes = sorted({r["mode"] for r in runs})
        print(f"  info agent modes used: {modes}" + ("  (llm = your Foundry model answered; rules = the built-in fallback)" if url else ""))
        if not url:
            check(modes == ["rules"], "all runs in rules mode")
        ev = c.get(f"/api/v1/reports/{rid}/events").json()
        check({"outline_approved", "findings_approved", "deck_final", "new_version"} <= {e["kind"] for e in ev}, f"{len(ev)} events recorded")
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
