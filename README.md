# COE4 Committee Report Assistant: solution

> **Setting this up on a new PC, or handing it to GitHub Copilot?** Read [`COPILOT_START_HERE.md`](COPILOT_START_HERE.md). It has the three
> tasks in order (install and run everything, connect the Foundry model with your Azure sign-in, apply the Group UI colours and fonts)
> and a ready-to-paste prompt for each. `AGENTS.md` gives Copilot the standing rules of this repository.

Three services. The front end only talks to the backend; the backend is the only caller of the agents.

```
 Browser (React)          Backend (FastAPI)            Agents (FastAPI)
 committee-report-   -->  backend/   :8001        -->  agents/    :8002
 assistant/ :5173         API, storage, CORS           one endpoint per agent
```

| Folder | Service | Port | Job |
|---|---|---|---|
| `committee-report-assistant/` | Front end (React 18 + Vite) | 5173 (dev) / 8080 (Docker) | The three stages: Brief, Analysis, Report. **Demo** mode (built-in sample data) and **Live** mode (the real backend and agents, plus the Agent log tab) |
| `backend/` | FastAPI | 8001 | Controls the front end: API, committees and reports storage, calls the agents, hides agent failures from the UI |
| `agents/` | FastAPI | 8002 | The **18 agents** (Brief, reading, research, analysis, slides; stateless, JSON in / JSON out). Each runs on your model (Foundry) or on a built-in rules version |

The **orchestrator** (plain Python state machine and job runner) lives in the backend. Agents never call each other; the orchestrator
calls them in order and keeps all state in the **case workspace** (database + files, see `backend/README.md`). The author does two things:
write the **brief** (and approve the outline), then work in one **draft** where research, analysis and slides come together. There
are no sign-offs: everything is saved as the author works, the saved draft is the final version, and downloading it is recorded.

## Run it

Windows without Docker (needs Python 3.12+ and Node 20+):
```
.\start-all.ps1 -Install     # once: venvs, pip install, npm install
.\start-all.ps1              # opens three windows
```
Then open http://localhost:5173 . API docs: http://localhost:8001/docs and http://localhost:8002/docs .

With Docker: `docker compose up --build`, then open http://localhost:8080 .

Manually, one terminal each:
```
cd agents  && pip install -r requirements.txt && uvicorn app.main:app --port 8002 --reload
cd backend && pip install -r requirements.txt && uvicorn app.main:app --port 8001 --reload
cd committee-report-assistant && npm install && npm run dev
```
Tests: `pip install -r requirements-dev.txt && pytest` inside `agents/` (64 tests) or `backend/` (55 tests); the backend tests start the agents service themselves.

## What is connected today

Stage 1 (Brief):
- The brief goes front end -> `POST /api/v1/brief/assess` (backend) -> `POST /v1/brief/assess` (agent).
- The agent returns the score and label, a 2-3 line summary, up to 3 hints, up to 3 optional questions, and what it understood. Both cards in Stage 1 show this.
- German and English: the agent answers in the language the UI is in.
- Speech: the Speak button uses the browser's speech input (Chrome/Edge). See the privacy note below.
- If the backend or an agent is down, the front end silently uses its local logic, so nothing breaks and the page also works as a single file.

Stages 2 and 3 (Analysis, Report) run in the backend and, in **Live** mode, the front end uses them for everything:

- **Demo | Live toggle** (top bar, remembered in the browser). Demo keeps the built-in sample data and sends nothing. Live works on the backend: create a
  report, brief, upload files, outline, interview, research and analysis, review of claims and evidence, slides, export. Live shows an extra tab, **Agent log**:
  which agent did what, on the model or on rules, tokens and time per agent, every call with its input and output, and the decisions of the run.
- **Ingestion** (`backend/app/services/ingest.py`, `core/parsers`): any PDF (text, image, scanned), Word, PowerPoint, Excel, e-mail (.eml/.msg with attachments), image, text.
  Code does the reading and the structure; pages that code cannot read (scans, images, figures) go to the `document-reader` agent (vision model). Every file gets a quality
  report (read completely / in part / hardly readable, with warnings) that the page shows.
- **Exhaustive analysis**: all text of all sources is processed in blocks (parallel), evidence is extracted with verbatim quotes and locators, and the section analyst also
  reads the raw passages that matter for its section (retrieval) and may add evidence of its own that is checked against the passage text.
- **Web research is on for every report** (the author can switch it off under “More options”; `ALLOW_WEB=false` stops fetching cited pages): Foundry's own web search tool, no Bing key, no extra credentials. Every page used is listed as a source. The planner always plans external context (market, benchmarks, regulation) next to the internal sources, and a guard rail adds it if the model forgets.
- **Research is planned per topic, not from a fixed list.** The author's own material is read first; the research planner then sees what it covers and decides where to look (web, SharePoint, mail, Teams, SAP, Jira, Confluence: whatever the source catalogue in `backend/app/core/connectors.py` offers). After extraction it runs again in `gaps` mode for the sections that are still thin (`GAP_ROUNDS`, default 1). Every round, its reasoning and what it found are shown in the Research plan tab. A new connector needs a catalogue entry and a class with `available()`, `search()`, `fetch()`.
- **Asset library.** Pictures are cut out of PDF pages at figure size with their caption (embedded bitmaps and vector charts), taken from Word, PowerPoint, mails and cited web pages; PowerPoint charts keep their exact numbers. The vision model looks at each picture (what it is, usable or not, crop box, chart data); chart numbers become evidence, so the chart is redrawn natively from verified numbers. The curator chooses from the whole catalogue; “Use” / “Skip” of the author always wins. Web pictures are marked “check rights”.
- **Slides**: one JSON per slide (`layout`, `blocks`, text sizes fitted on the server). The page and the PowerPoint file are drawn from the same JSON, so they match
  (a test checks every title, bullet, key figure and table cell). Charts are native PowerPoint charts. Numbers on a slide must come from the evidence or a calculation.
  Edit text right on the slide, or write a comment per slide for the slide editor (undo is kept); add, move, delete slides; download = what you see.
- Template: upload a .pptx and its colours, fonts and structure are used. Without a template the template analyst advises a structure that fits topic and committee.

Committees and reports are stored in the database; `PUT /api/v1/reports/{id}/workspace` still autosaves the Demo mode's state.

## Try the whole flow (no front end needed)
```
python e2e/make_samples.py sample-data          # template, offer (docx), cost model (xlsx), risks, plan: consistent numbers
python e2e/run_e2e.py --keep                    # starts both services on free ports, runs every step with checks, keeps e2e/out/deck_v1.pptx, deck_v2.pptx
python e2e/run_e2e.py --url http://localhost:8001   # same flow against the services you started (leaves a report in your database)
```
The run covers: upload -> outline -> interview -> research, analysis and deck in one go -> a wrong number is flagged and kept out of the
slides -> slide edit -> Ask AI on a section with undo -> PowerPoint with native chart, sources slide and short sections sharing a page. It needs no model: agents run in rules mode.
With your Foundry settings in `agents/.env` the same script runs on the model (`info agent modes used` shows which).

## Local first, Foundry later
| Today (local) | Later |
|---|---|
| agents: FastAPI + `openai` SDK against your endpoint, or rules | the same `POST /v1/agents/{id}/run` contract as Foundry agents / functions |
| SQLite `backend/data/coe4.db` | PostgreSQL: set `DATABASE_URL` |
| local file store `backend/data/files` | Azure Blob: implement the 4 methods in `backend/app/core/storage.py` |
| connectors = folders `backend/data/connectors/<kind>/` | SharePoint, Exchange, Teams, SAP in `backend/app/core/connectors.py` |
| threads in the backend | a queue / Durable Functions behind `services/jobs.py` |

Not verified yet: any call to a real Foundry model for the pipeline agents (including the web search tool and the vision model); only the SDK wiring was tested with a fake server. The model paths are tested with scripted model answers, including wrong ones.
Foundry settings are environment variables only (`agents/.env`): endpoint or resource + project name, deployment name, optional tenant id. No key is needed: with `AZURE_USE_ENTRA_ID=true` the first call opens a browser sign-in, after that the account is remembered (see `agents/README.md`).

## API overview

Backend (8001): `GET /health`, `GET /api/v1/agents`, `POST /api/v1/brief/assess`, committees and reports, and the workflow under `/api/v1/reports/{id}/...` (table in `backend/README.md`).
Errors: 503 when the agents service is down, 502 when an agent returns an error.
Agents (8002): `GET /health`, `GET /v1/agents`, `POST /v1/brief/assess`, `POST /v1/agents/{id}/run`, `GET /v1/agents/{id}/schema`.

The request and response models are in `agents/app/schemas.py` and are copied to `backend/app/schemas.py`. Services do not import each other; change both copies together (later: a shared package or OpenAPI-generated client).

## Things to know

- **Speech and privacy.** Chrome's speech recognition sends the audio to Google. The requirement "stays in the VW environment" is not met until this is replaced by Azure Speech in the VW tenant. Use only mock data until then.
- **The Brief agent uses a language model when configured.** Put your Foundry / Azure OpenAI settings in `agents/.env` (template: `agents/.env.example`), restart the agents service and check `http://localhost:8002/health/llm`. Without settings, or if the model fails, the built-in rules agent answers (`agent.mode: rules`), so the app never breaks. The text of the brief (not file contents) is sent to the model you configure.
- **CORS.** The backend allows `localhost:5173/4173` and the `null` origin (for opening `dist/index.html` from disk). Remove `null` outside demos (`CORS_ORIGINS`).
- No login yet. The database has the tables for versions and audit; users and roles are not built.
- Data from your uploads and the agent inputs/outputs are stored in `backend/data` (also in `agent_runs`). Delete a report and its files and audit trail go with it. Do not commit `backend/data` (it is in `.gitignore`).
