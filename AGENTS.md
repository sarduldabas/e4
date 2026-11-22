# Instructions for GitHub Copilot and other coding assistants (AGENTS.md)

This file is read automatically. The full, step-by-step task descriptions are in **`COPILOT_START_HERE.md`** (repository root). When the user
asks you to install and run the project, connect the Foundry model, or apply the Group UI colours and fonts, open that file and follow
the matching task. Do not start a task the user did not ask for.

## The project
COE4 Committee Report Assistant: a tool that turns a committee brief and source documents into a checked, traceable PowerPoint report.
Three services: `committee-report-assistant/` (React + Vite, port 5173) -> `backend/` (FastAPI, port 8001) -> `agents/` (FastAPI, port 8002).
The front end only calls the backend; only the backend calls the agents; agents never call each other.

## Commands (Windows PowerShell, from the repository root)
- Install once: `.\start-all.ps1 -Install`. Start all three services: `.\start-all.ps1` (or double-click `run.bat`).
- Tests: `agents\.venv\Scripts\python.exe -m pytest agents -q` (48) and `backend\.venv\Scripts\python.exe -m pytest backend -q` (26).
- Whole workflow against the running services: `backend\.venv\Scripts\python.exe e2e\run_e2e.py --url http://localhost:8001`.
- Front end: inside `committee-report-assistant/`: `npm run dev`, `npm run build`.

## Rules
- Never commit secrets. `agents/.env` holds the Foundry settings and is git-ignored. Do not print keys or tokens.
- Do not invent endpoints, deployment names, tenant ids or URLs; ask the user.
- Keep changes small and in scope. No refactoring on the side, no agent frameworks (the owner wants plain Python loops), no new dependencies without asking.
- Every agent has a model path and a rules path. Keep both. Do not weaken the checks in an agent's `clean()` (unknown ids, quotes not verbatim in the text, numbers not in the quote are dropped), and do not remove the rules fallback.
- A claim must always trace claim -> evidence -> source -> locator. Parsing, arithmetic, charts and PowerPoint creation are done by code, never by the model.
- The request and response models exist in two copies (`agents/app/schemas.py` and `backend/app/schemas.py`). Change both together.
- UI text goes through `t('English text')` with the German line in `committee-report-assistant/src/i18n.de.js`. German is the default language.
- For the Group UI work, change colour and font tokens only (`committee-report-assistant/VW_BRANDING.md`).
- Run the tests of the service you changed and report honestly what you ran and what failed. A silent fallback to `mode: rules` is not a pass of a model test.
- Do not push to GitHub unless the user asks.
