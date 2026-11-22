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
| `committee-report-assistant/` | Front end (React 18 + Vite) | 5173 (dev) / 8080 (Docker) | The three stages: Brief, Analysis, Report |
| `backend/` | FastAPI | 8001 | Controls the front end: API, committees and reports storage, calls the agents, hides agent failures from the UI |
| `agents/` | FastAPI | 8002 | The agents: the **Brief agent** (Stage 1) and the **12 pipeline agents** (stateless, JSON in / JSON out). Each runs on your model (Foundry) or on a built-in rules version |

The **orchestrator** (plain Python state machine and job runner) lives in the backend. Agents never call each other; the orchestrator
calls them in order, keeps all state in the **case workspace** (database + files, see `backend/README.md`) and enforces the three
checkpoints (outline, findings, deck).

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
Tests: `pip install -r requirements-dev.txt && pytest` inside `agents/` (48 tests) or `backend/` (26 tests); the backend tests start the agents service themselves.

## What is connected today

Stage 1 (Brief):
- The brief goes front end -> `POST /api/v1/brief/assess` (backend) -> `POST /v1/brief/assess` (agent).
- The agent returns the score and label, a 2-3 line summary, up to 3 hints, up to 3 optional questions, and what it understood. Both cards in Stage 1 show this.
- German and English: the agent answers in the language the UI is in.
- Speech: the Speak button uses the browser's speech input (Chrome/Edge). See the privacy note below.
- If the backend or an agent is down, the front end silently uses its local logic, so nothing breaks and the page also works as a single file.

Stages 2 and 3 (Analysis, Report): the **whole pipeline now runs in the backend** and can be tried over the API (`/docs`) or with the
demo script below. The front end screens for these stages still show mock data; wiring them to `/api/v1/reports/{id}/...` is the
next step. Committees and reports are stored in the database; `PUT /api/v1/reports/{id}/workspace` still autosaves the front end's state.

## Try the whole flow (no front end needed)
```
python e2e/make_samples.py sample-data          # template, offer (docx), cost model (xlsx), risks, plan: consistent numbers
python e2e/run_e2e.py --keep                    # starts both services on free ports, runs every step with checks, keeps e2e/out/deck_v1.pptx, deck_v2.pptx
python e2e/run_e2e.py --url http://localhost:8001   # same flow against the services you started (leaves a report in your database)
```
The run covers: upload -> outline -> interview -> research -> findings (a wrong number is flagged and blocks generation) -> deck with
native chart and sources slide -> feedback -> version 2 with a "changes since v1" slide. It needs no model: agents run in rules mode.
With your Foundry settings in `agents/.env` the same script runs on the model (`info agent modes used` shows which).

## Local first, Foundry later
| Today (local) | Later |
|---|---|
| agents: FastAPI + `openai` SDK against your endpoint, or rules | the same `POST /v1/agents/{id}/run` contract as Foundry agents / functions |
| SQLite `backend/data/coe4.db` | PostgreSQL: set `DATABASE_URL` |
| local file store `backend/data/files` | Azure Blob: implement the 4 methods in `backend/app/core/storage.py` |
| connectors = folders `backend/data/connectors/<kind>/` | SharePoint, Exchange, Teams, SAP in `backend/app/core/connectors.py` |
| threads in the backend | a queue / Durable Functions behind `services/jobs.py` |

Not verified yet: any call to a real Foundry model for the 12 pipeline agents (only the Brief agent was ever pointed at a model endpoint, and
only the SDK wiring was tested with a fake server). The model paths are tested with scripted model answers, including wrong ones.
Sign-in to Foundry: an API key, or your Azure account (`AZURE_USE_ENTRA_ID=true`: Azure CLI `az login` or a browser tab, see `agents/README.md`).

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
