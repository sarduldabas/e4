# COE4 Committee Report Assistant: solution

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
| `agents/` | FastAPI | 8002 | The agents. Today: the **Brief agent** (Stage 1). Seven more are listed as planned in `GET /v1/agents` |

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
Tests: `pip install -r requirements-dev.txt && pytest` inside `agents/` or `backend/`.

## What is connected today

Stage 1 (Brief):
- The brief goes front end -> `POST /api/v1/brief/assess` (backend) -> `POST /v1/brief/assess` (agent).
- The agent returns the score and label, a 2-3 line summary, up to 3 hints, up to 3 optional questions, and what it understood. Both cards in Stage 1 show this.
- German and English: the agent answers in the language the UI is in.
- Speech: the Speak button uses the browser's speech input (Chrome/Edge). See the privacy note below.
- If the backend or an agent is down, the front end silently uses its local logic, so nothing breaks and the page also works as a single file.

Ready in the backend but not yet used by the front end: `GET /api/v1/committees`, reports (`GET/POST /api/v1/reports`, `GET/DELETE /api/v1/reports/{id}`) and `PUT /api/v1/reports/{id}/workspace` for autosave. Storage is a JSON file (`DATA_DIR`), to be replaced by a database.

Stages 2 and 3 (Analysis, Report) still run on mock data in the front end.

## API overview

Backend (8001): `GET /health`, `GET /api/v1/agents`, `POST /api/v1/brief/assess`, committees and reports as above.
Errors: 503 when the agents service is down, 502 when an agent returns an error.
Agents (8002): `GET /health`, `GET /v1/agents`, `POST /v1/brief/assess`.

The request and response models are in `agents/app/schemas.py` and are copied to `backend/app/schemas.py`. Services do not import each other; change both copies together (later: a shared package or OpenAPI-generated client).

## Things to know

- **Speech and privacy.** Chrome's speech recognition sends the audio to Google. The requirement "stays in the VW environment" is not met until this is replaced by Azure Speech in the VW tenant. Use only mock data until then.
- **The Brief agent is rule-based** (deterministic, tested, no model call). The contract already allows an LLM version (`agent.mode` is `rules` or `llm`), e.g. Azure OpenAI / Foundry, behind the same endpoint.
- **CORS.** The backend allows `localhost:5173/4173` and the `null` origin (for opening `dist/index.html` from disk). Remove `null` outside demos (`CORS_ORIGINS`).
- No login yet. Multi-user, roles and versions on the server come with the database.
