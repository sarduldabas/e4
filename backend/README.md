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
State machine: `SETUP → OUTLINE_REVIEW → COLLECTING → ANALYSING → (FINDINGS_REVIEW, transient) → GENERATING → DECK_REVIEW`. There is no final state:
the draft in `DECK_REVIEW` is saved as it is edited, and downloading it is recorded (`deck_exported`). A step in the wrong state answers `409`.

| Step | Endpoint | Agent(s) |
|---|---|---|
| brief, files | `PUT /case`, `POST /files` (role template / source / prior_report) | – |
| outline | `POST /outline/propose`, `PUT /outline` | template-analyst |
| interview | `POST /interview/turn` | interviewer |
| **approve the outline = the draft is made** | `POST /outline/approve` → one job | document-reader (scans, images), evidence-extractor (all text, in blocks) for the author's own material first, then source-planner (plan for this topic), web-search*, source-screener, a gap round (source-planner in gaps mode), asset-analyst (vision), asset-curator, then per section section-analyst (plan, write) + verifier (max 2 rounds), red-team over the whole draft, then storyline-architect and slide-writer (verified claims are taken in automatically; the rest stay out of the slides and are listed) |
| evidence | `GET /findings`, `PATCH /claims/{id}`, `POST /claims/{id}/include` (take a left-out finding into its slide), `POST /flags/{id}/resolve` (a note is optional) | verifier again on edited claims; slide-editor for `include` |
| the draft | `GET /deck` (slides with their claims, evidence and calculations, `attention`, `export`, `ai_undo`), `PATCH /deck/slides/{id}` (the whole slide spec), `POST /deck/slides/{id}/revise`, `POST .../undo`, `POST /deck/slides`, `PUT .../position`, `DELETE`, `GET /deck/download`; layouts: `GET /api/v1/slide-layouts` | slide-editor (PowerPoint is built by code from the same slide JSON) |
| Ask AI | `POST /deck/ask` `{text, scope: slide \| section \| deck, slide_id, section_key}` → a slide answers at once, a section or the whole deck runs as a job; `POST /deck/ask/undo` (one step) | slide-editor (slide) or feedback-interpreter, then only what the request touches is re-researched and re-written |
| rebuild | `POST /deck/build` (retry after a failed job), `POST /research/rerun` | – |
| audit | `GET /events`, `GET /agent-runs?io=true`, `GET /agent-runs/summary`, `GET /sources`, `GET /jobs/{id}`; status for the page: `GET /api/v1/system/status` | – |

\* on unless the report has web research switched off (`use_web`, default on); `ALLOW_WEB` (default true) only decides whether cited pages are fetched and read in full; links named in the brief are fetched when it is on.

Rules the orchestrator enforces: nothing blocks the author (an open flag or a claim the verifier did not support is shown under *needs attention*, and the claim stays out of the slides); edited claims are verified again; every slide bullet must point to an approved claim;
chart numbers must be numbers from the ledger; calculations are computed by `app/core/calc.py`, not by a model;
Ask AI on a section or the whole deck first stores a snapshot (the last 5 are kept) and then redoes only what it touches; hand edits in a re-written section are replaced, `POST /deck/ask/undo` restores them.

**Export packing** (`app/core/slides/pack.py`, PowerPoint only; the web view keeps one slide per section slide): consecutive text slides of different sections share a page while the first is less than 75% full and the sum fits (at most 3 parts, 10 lines); each part's title becomes a bold heading line. `deck_view` reports `shares_with_next` and `export.slides` so the screen says how many pages the file will have.

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

## Sample reports

A fresh database starts **empty** in Live mode: only the committees and their dates (master data) are seeded.
The three sample reports of the Demo are not created. To get them for a local look-around, set
`SEED_SAMPLE_REPORTS=true` before the first start (an existing database keeps what it has).
Live mode uses the same screens as Demo; the only difference is that everything comes from the agents and the backend.
