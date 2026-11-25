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
| **checkpoint 1** | `POST /outline/approve` → job | document-reader (scans, images), evidence-extractor (all text, in blocks) for the author's own material first, then source-planner (plan for this topic), web-search*, source-screener, a gap round (source-planner in gaps mode), asset-analyst (vision), asset-curator, then per section section-analyst (plan, write) + verifier (max 2 rounds), then red-team |
| **checkpoint 2** | `GET /findings`, `PATCH /claims/{id}`, `POST /flags/{id}/resolve`, `POST /findings/approve` → job | verifier again on edited claims; storyline-architect, slide-writer |
| **checkpoint 3** | `GET /deck`, `PATCH /deck/slides/{id}` (the whole slide spec), `POST /deck/slides/{id}/revise` (a comment), `POST .../undo`, `POST /deck/slides`, `PUT .../position`, `DELETE`, `GET /deck/download`, `POST /deck/finalize`; layouts: `GET /api/v1/slide-layouts` | slide-editor (PowerPoint is built by code from the same slide JSON) |
| next version | `POST /feedback`, `POST /feedback/{id}/apply` → job | feedback-interpreter, then only what the feedback touches |
| audit | `GET /events`, `GET /agent-runs?io=true`, `GET /agent-runs/summary`, `GET /sources`, `GET /jobs/{id}`; status for the page: `GET /api/v1/system/status` | – |

\* on unless the report has web research switched off (`use_web`, default on); `ALLOW_WEB` (default true) only decides whether cited pages are fetched and read in full; links named in the brief are fetched when it is on.

Rules the orchestrator enforces: generation is blocked while a **blocker** flag is open (a blocker can be accepted only
with a written reason, which is kept); edited claims are verified again; every slide bullet must point to an approved claim;
chart numbers must be numbers from the ledger; calculations are computed by `app/core/calc.py`, not by a model;
v2 starts as a copy of v1's approved claims and slides, and only the sections the feedback touches are redone.

## Settings
See `.env.example`: services, storage, `ALLOW_WEB`, `GAP_ROUNDS`, `MAX_ASSETS_ANALYSED`, and the reading limits `PARALLEL_CALLS`, `MAX_VISION_PAGES`, `EXTRACT_BATCH_CHARS`, `MAX_EXTRACT_CHARS`, `PASSAGE_CHARS`.

## Structure
`app/main.py` (app factory), `app/db.py`, `app/models.py`, `app/routers/` (brief, reports, workflow, system),
`app/services/` (orchestrator, outline, ingest, collect, retrieval, analyse, numbers, generate, slides, feedback, jobs, runner, ctx),
`app/core/` (parsers, calc, slides: layouts, fit, spec, theme, render_pptx; connectors, storage), `app/agents_client.py` (brief assessment), `app/seed.py`.


## Research plan and asset library endpoints
- `GET /api/v1/reports/{id}/research-plan`: the planner's strategy, needs and queries per round, what each round found, web notes
- `GET /api/v1/reports/{id}/assets`: every picture, chart and table with the analyst's description, treatment (use / redraw / discard) and the curator's choice
- `PATCH /api/v1/reports/{id}/assets/{asset_id}`: `user_choice` (`use`, `skip`, null), `section_key`, `caption`
- `GET /api/v1/reports/{id}/assets/{asset_id}`: the picture itself
