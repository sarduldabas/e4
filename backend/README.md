# Backend service

FastAPI service. Port 8001. It serves the front end, **owns the case workspace** (database and files) and runs the
**orchestrator** that calls the agents. It contains no agent logic.

```
pip install -r requirements.txt
cp .env.example .env        # optional
uvicorn app.main:app --port 8001 --reload
pip install -r requirements-dev.txt && pytest      # also starts the agents service in rules mode (needs ../agents)
```

## The case workspace (the "memory")
Agents are stateless: they get everything they need in each request and keep nothing. What the solution *remembers*
lives here, per report (a report is a case):

| Where | What |
|---|---|
| SQLite `data/coe4.db` (18 tables, `app/models.py`) | the ledger: brief, outline, interview turns, sources, **evidence** (statement + verbatim quote + locator + source), calculations, **claims** (each with its evidence and calculation ids), verifier/red-team flags, slides, decks, versions, jobs, **agent_runs** (input and output of every agent call), events (who approved what) |
| `data/files/reports/<id>/` | uploads, the parsed text of each source (`parsed/`), images (`assets/`), generated decks (`decks/v1.pptx`) |
| `data/connectors/<kind>/` | demo sources a connector can search: put files into `files/`, `sharepoint/`, `mail/`, `teams/`, `sap/` |

Moving on: `DATABASE_URL` points the same tables at PostgreSQL; `app/core/storage.py` (4 methods) is the only place to swap
for Azure Blob; `app/core/connectors.py` is where SharePoint, Exchange, Teams and SAP connectors go.

## Workflow (all under `/api/v1/reports/{id}`)
State machine: `SETUP → OUTLINE_REVIEW → COLLECTING → ANALYSING → FINDINGS_REVIEW → GENERATING → DECK_REVIEW → FINAL → FEEDBACK → …`
A step in the wrong state answers `409`.

| Step | Endpoint | Agent(s) |
|---|---|---|
| brief, files | `PUT /case`, `POST /files` (role template / source / prior_report) | – |
| outline | `POST /outline/propose`, `PUT /outline` | template-analyst |
| interview | `POST /interview/turn` | interviewer |
| **checkpoint 1** | `POST /outline/approve` → job | source-planner, source-screener, evidence-extractor, web-researcher*, asset-curator, then per section section-analyst (plan, write) + verifier (max 2 rounds), then red-team |
| **checkpoint 2** | `GET /findings`, `PATCH /claims/{id}`, `POST /flags/{id}/resolve`, `POST /findings/approve` → job | verifier again on edited claims; slide-writer |
| **checkpoint 3** | `GET /deck`, `PATCH /deck/slides/{id}`, `GET /deck/download`, `POST /deck/finalize` | – (PowerPoint is built by code) |
| next version | `POST /feedback`, `POST /feedback/{id}/apply` → job | feedback-interpreter, then only what the feedback touches |
| audit | `GET /events`, `GET /agent-runs?io=true`, `GET /sources`, `GET /jobs/{id}` | – |

\* only when `ALLOW_WEB=true` and the brief names links.

Rules the orchestrator enforces: generation is blocked while a **blocker** flag is open (a blocker can be accepted only
with a written reason, which is kept); edited claims are verified again; every slide bullet must point to an approved claim;
chart numbers must be numbers from the ledger; calculations are computed by `app/core/calc.py`, not by a model;
v2 starts as a copy of v1's approved claims and slides, and only the sections the feedback touches are redone.

## Settings
See `.env.example`.

## Structure
`app/main.py` (app factory), `app/db.py`, `app/models.py`, `app/routers/` (brief, reports, workflow, system),
`app/services/` (orchestrator, outline, collect, analyse, generate, feedback, jobs, runner, ctx),
`app/core/` (parsers, calc, deck, connectors, storage), `app/agents_client.py` (brief assessment), `app/seed.py`.
