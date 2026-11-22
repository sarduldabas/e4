
## Language (added 23.11.2026)
- German is the default UI language; DE | EN toggle at the top right of the nav bar. Everything else unchanged.
- Implementation: `src/i18n.js` (`t`, `num`), `src/i18n.de.js` (about 620 German strings, formal Sie). Details in README, section "Language".
- Slides, charts, sample content and chat replies switch live. Typed text stays as typed.
- Open: native-speaker review of the German wording (VW terminology, e.g. Gremium, Review-Gate, Lastenheft-style terms) before sample-user tests.
- Open: the demo language is not remembered between sessions (always starts in German). Add persistence if wanted.

## Three services (backend + agents added)
- Layout: `committee-report-assistant/` (front end, 5173), `backend/` (FastAPI, 8001), `agents/` (FastAPI, 8002). Start: `.\start-all.ps1 -Install` once, then `.\start-all.ps1`. Details in `README.md`.
- Wired: Stage 1 Brief. Front end -> backend `/api/v1/brief/assess` -> Brief agent (language model via Foundry/Azure OpenAI when `agents/.env` is filled in; rules agent as fallback) returns score, 2-3 line summary, hints, up to 3 optional questions. Offline fallback to local logic if services are down.
- Speak button uses the browser speech input (Chrome/Edge). Open: Chrome sends audio to Google, so replace with Azure Speech inside the VW tenant before real data.
- Ready in backend, not yet used by front end: committees, reports CRUD, workspace autosave (JSON store, DB later).
- Next: wire Analysis (Stage 2) agents (reader, extractor, researcher, analyst, cross-checker, challenger), LLM version of the Brief agent, Azure Speech, DB + login, slide builder (Stage 3).

- LLM: `agents/.env` (copy of `.env.example`) holds endpoint, deployment name and key. Check with http://localhost:8002/health/llm. Score formula stays in code; the model supplies understanding, summary, hints and questions. Not yet verified against the real Foundry endpoint.

## 2026-11-23: all 12 agents, database, case workspace and orchestrator (local)
- agents/: 12 pipeline agents (template-analyst, interviewer, source-planner, source-screener, web-researcher, evidence-extractor, asset-curator, section-analyst, verifier, red-team, slide-writer, feedback-interpreter) + Brief agent. Each has a model path and a rules path; `POST /v1/agents/{id}/run`.
- backend/: SQLite ledger (18 tables) + local file store = the "memory" (agents stay stateless); orchestrator state machine with 3 checkpoints; jobs; parsers; calculation engine (code); PPTX builder (code); local connector folders under backend/data/connectors/<kind>/.
- Old backend/data/reports.json is no longer used (reports now in backend/data/coe4.db; demo reports re-seeded). Old store.py moved to _to_delete/.
- e2e/: `python e2e/run_e2e.py --keep` runs the whole flow with checks; `--url http://localhost:8001` runs it against the services started by run.bat.
- NOT verified: any real Foundry call for the 12 pipeline agents. Front-end stages 2/3 still show mock data (not wired yet).
- Later: DATABASE_URL -> PostgreSQL, storage.py -> Blob, connectors.py -> SharePoint/Exchange/Teams/SAP, jobs.py -> queue.

## 2026-11-23: hand-over to GitHub Copilot on another PC
- `COPILOT_START_HERE.md` (repo root) = the three tasks in order with checks and ready-to-paste prompts: (1) install and run all services locally, (2) connect the agents to the Foundry model, (3) Group UI colours and fonts. `AGENTS.md` (repo root) = standing rules for Copilot.
- Foundry sign-in: `AZURE_USE_ENTRA_ID=true` now signs in once per service start: environment / managed identity / VS Code / Azure CLI (`az login`) / ... and, last, a browser tab (`AZURE_ENTRA_BROWSER=true`, optional `AZURE_TENANT_ID`). Same experience as the colleague's chat app. Trigger it on purpose with http://localhost:8002/health/llm. Tested with a fake credential only; never against real Azure.
- `.env.example`: LLM_TIMEOUT_SECONDS now 60 (pipeline agents read whole documents). Scope hint for Foundry project URLs: `AZURE_OPENAI_ENTRA_SCOPE=https://ai.azure.com/.default`.
- `committee-report-assistant/VW_BRANDING.md`: paths and commands now say explicitly they are relative to the front-end folder. Group UI URL still to be given to Copilot in chat.
- Tests: agents 48, backend 26. Still open: real Foundry run of the 12 pipeline agents, front-end stages 2/3, Azure Speech, web researcher on real pages.
