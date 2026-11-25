# Start here (for GitHub Copilot and any other coding assistant)

You are working in the repository of the **COE4 Committee Report Assistant**. The owner is Sardul Dabas (Product Delivery
Manager, VW Group Digital Solutions India). He will ask you for **three tasks, in this order**. Do them one at a time, and
finish each one, with its checks, before you start the next.

| # | Task | Section |
|---|---|---|
| 1 | Install everything and run all services on this PC | [Task 1](#task-1-install-and-run-everything-locally) |
| 2 | Connect the agents to the real Foundry model | [Task 2](#task-2-connect-the-agents-to-the-foundry-model) |
| 3 | Switch colours and fonts to the Volkswagen Group UI | [Task 3](#task-3-group-ui-colours-and-fonts) |

Ready-to-paste prompts, one per task, are at the end of this file.

## What this repository is

Three services. The front end only talks to the backend; the backend is the only caller of the agents.

```
Browser (React + Vite)           Backend (FastAPI)                Agents (FastAPI)
committee-report-assistant/ -->  backend/   port 8001      -->   agents/   port 8002
port 5173                        API, database, orchestrator      13 agents, one endpoint each
```

- **agents/**: the Brief agent plus 16 pipeline agents (17 in total). Stateless, JSON in and JSON out. Each agent has a **model path**
  (Foundry / Azure OpenAI) and a **rules path** (plain Python, no model). Mode `auto` uses the model when
  `agents/.env` is complete and otherwise the rules; the response says which one answered (`mode` and `note`).
- **backend/**: the orchestrator (a plain Python state machine plus a thread job runner), the SQLite database and file store (the
  "case workspace", which is the memory; agents stay stateless), parsers, the calculation engine and the PowerPoint builder.
  Details: `backend/README.md`.
- **committee-report-assistant/**: the React front end. German is the default language, English is a toggle.
  Stage 1 (Brief) is wired to the backend. Stages 2 and 3 still show mock data (see "Not done yet").
- **e2e/**: `run_e2e.py` drives the whole workflow over HTTP and checks it.
- Design rules that must keep holding: agents never call each other; every claim traces back claim -> evidence -> source ->
  locator; parsing, arithmetic, charts and PowerPoint are code, never the model; at most 2 analyst-and-verifier rounds; deck
  generation is blocked while blocker flags are open; three human checkpoints (outline, findings, deck).

More detail: `README.md` (root), `agents/README.md`, `backend/README.md`, `PROJECT_NOTES.md`.

## Rules for you

1. **Never put secrets in git.** `agents/.env` is ignored; keep it that way. Do not paste keys, tokens or tenant ids into any tracked file, log or chat message.
2. **Do not invent values.** Endpoint URLs, deployment names, tenant ids and design-system URLs come from the user. If you do not have one, ask.
3. **Do not change what you were not asked to change.** No refactoring, no new frameworks, no renaming. The owner prefers plain Python loops over agent frameworks: do not add LangChain, AutoGen, Semantic Kernel or similar.
4. **Keep the tests green.** After a code change run the tests of the service you touched (commands below). Do not delete or weaken a test or a guard rail to make something pass. If a test fails, find out why and tell the user.
5. **Windows PowerShell** is the shell. Use `\` paths and `.venv\Scripts\python.exe`, not `source` or `/`.
6. **Say what you did and what you could not do**, in plain words, at the end of each task. Do not report something as working unless you ran it and saw it work.
7. Commit in small steps with clear messages. Do not push unless the user tells you to.

---

## Task 1: Install and run everything locally

Goal: after a fresh `git clone`, all three services run on this PC, all 13 agents answer, and the tests and the demo flow pass.
No model and no Azure account are needed for this task (agents run in rules mode).

### 1.1 Prerequisites (check, install only what is missing)

```powershell
git --version
python --version      # needs 3.12 or newer
node --version        # needs 20 or newer
npm --version
```

Install what is missing, then open a new terminal so PATH is refreshed:

```powershell
winget install -e --id Git.Git
winget install -e --id Python.Python.3.12
winget install -e --id OpenJS.NodeJS.LTS
```

Windows can ship a "python" shortcut that opens the Microsoft Store instead of Python. If `python --version` opens the Store or prints nothing, install Python as above and make sure it comes first on PATH.

### 1.2 Install and start

From the repository root (the folder that contains `run.bat`):

```powershell
.\start-all.ps1 -Install      # once: creates agents\.venv and backend\.venv, pip install, npm install (a few minutes)
.\start-all.ps1               # opens three PowerShell windows: agents, backend, front end
```

`run.bat` does both steps and then opens the browser; it can be double-clicked. If PowerShell blocks the script, run it as
`powershell -NoProfile -ExecutionPolicy Bypass -File .\start-all.ps1` (this is what `run.bat` does). The script frees ports
5173, 8001 and 8002 before it starts; it stops whatever listens on them.

If an install fails because of the company network (pip or npm cannot reach the package index), **ask the user** for the proxy or internal index to use. Do not change global pip or npm settings on your own.

### 1.3 Check that it works

Wait about 15 seconds after starting, then:

```powershell
Invoke-RestMethod http://localhost:8002/health        # status ok
Invoke-RestMethod http://localhost:8001/health        # status ok
Invoke-RestMethod http://localhost:8002/v1/agents | Select-Object id, mode
```

Expected: 18 agents listed (the Brief agent and 17 pipeline agents) and every `mode` is `rules`, because no model is configured yet. (`/health` also lists them under `agents_available`.)
Open http://localhost:5173 : the app starts in German; the Brief stage loads. The API docs are at http://localhost:8001/docs and http://localhost:8002/docs.

Run the tests (about 1 minute). `-m pytest` needs the dev packages first:

```powershell
agents\.venv\Scripts\python.exe -m pip install -r agents\requirements-dev.txt
agents\.venv\Scripts\python.exe -m pytest agents -q        # expected: 48 passed
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
backend\.venv\Scripts\python.exe -m pytest backend -q      # expected: 26 passed
```

Run the pytest commands from the repository root as written (the backend tests start their own agents service).

Run the whole workflow against the running services (upload, outline, interview, research, findings, deck, feedback, version 2):

```powershell
backend\.venv\Scripts\python.exe e2e\run_e2e.py --url http://localhost:8001
```

Expected: every step prints a check and the run ends without an error. It leaves one demo report in the database; that is fine.
The front end build also has to work: `cd committee-report-assistant; npm run build`.

### 1.4 Done when

- The three services answer, 13 agents are listed in `rules` mode, both test suites pass, the e2e run passes, `npm run build` passes.
- Report to the user: versions of Python and Node, what you installed, and anything that did not work.

Common problems: a port is busy (the start script frees 5173, 8001 and 8002; if another program needs them, tell the user), `pip install`
fails on a package (read the error; do not pin random versions), a window closes immediately (start the command by hand in a terminal to see the error).

---

## Task 2: Connect the agents to the Foundry model

Goal: the 18 agents answer with the real model (`mode: llm`) instead of the rules, signing in with the user's Azure account
the way the colleague's chat app does. Task 1 must be finished first.

### 2.1 Ask the user for these values (do not guess)

- The Foundry / Azure OpenAI **endpoint**, as shown in Foundry (for example `https://<resource>.openai.azure.com` or `https://<resource>.services.ai.azure.com/api/projects/<project>`).
- The **deployment name** of the chat model (the name of the deployment in Foundry, not the model family). Optional: different deployments for the tiers `small`, `standard`, `strong` and `vision` (see `agents/.env.example`). With one deployment, leave the tiers empty.
- Whether the user signs in with an **API key** or with their **Azure account**. The expected answer is the Azure account: the colleague's app asked the user to install the Azure CLI and then opened a browser tab to sign in. That is Entra ID sign-in and is supported (below).
- Optional: the **tenant id**, only if the user has several directories. Instead of the endpoint the user may give the Foundry **resource name** and **project name** (`AZURE_AI_FOUNDRY_RESOURCE`, `AZURE_AI_PROJECT_NAME`); the endpoint is then built from them.
- No key is ever needed: after the first browser sign-in the account is remembered in `agents/.azure-auth-record.json`.

### 2.2 Create the settings file

```powershell
Copy-Item agents\.env.example agents\.env
```

Edit `agents\.env` (it is ignored by git; never commit it):

```
AGENT_MODE=llm                       # for the first tests: always try the model. Later: auto
AZURE_OPENAI_ENDPOINT=<from the user>
AZURE_OPENAI_DEPLOYMENT=<from the user>
AZURE_OPENAI_API_KEY=                # empty when signing in with the Azure account
AZURE_USE_ENTRA_ID=true
LLM_TIMEOUT_SECONDS=90               # the pipeline agents read whole documents
```

### 2.3 Sign in with the Azure account (Entra ID)

The agents service takes the first identity it finds: environment variables, managed identity, Visual Studio Code, Azure CLI, Azure PowerShell,
azd and, as the last resort, **a browser tab** (`AZURE_ENTRA_BROWSER=true`, the default). Recommended path:

1. Install the Azure CLI if `az --version` fails: `winget install -e --id Microsoft.AzureCLI`, then open a new terminal.
2. `az login` (a browser tab opens; the user picks the VW account). With several directories: `az login --tenant <tenant id>`.
3. `az account show` must print the account. Do not print or copy access tokens.

If the Azure CLI cannot be installed, skip it: the first model call opens the browser tab by itself and the user clicks the account.
The sign-in happens once per start of the agents service, on the first model call, and parallel calls wait for it (there is one tab, not many).
The user must be present to click.

### 2.4 Restart and test

Restart the agents service: the `.env` file is read only at startup, and `--reload` does not watch it. Close the agents window and run `.\start-all.ps1` again (it restarts all three). Then:

```powershell
Invoke-RestMethod http://localhost:8002/health/llm      # sign-in happens here if needed; expected: ok true and a latency
Invoke-RestMethod http://localhost:8002/v1/agents | Select-Object id, mode
```

Expected: `ok` is true and the agents show `llm`. If `/health/llm` returns an error text, use this table (the text never contains the key):

| Message contains | Likely cause | What to do |
|---|---|---|
| 401, "audience", "token" | Wrong token scope for this endpoint | For a Foundry project URL (`...services.ai.azure.com/api/projects/...`) set `AZURE_OPENAI_ENTRA_SCOPE=https://ai.azure.com/.default`. For a resource URL keep the default. Try the other if one fails. |
| 403, "PermissionDenied", "principal does not have access" | Role missing on the resource | Tell the user: their account needs a role such as *Cognitive Services OpenAI User* on the Foundry / Azure OpenAI resource. You cannot fix this from the code. |
| 404, "DeploymentNotFound" | Wrong deployment name or endpoint | Check the exact deployment name in Foundry with the user. |
| timeout | Model slow or network | Raise `LLM_TIMEOUT_SECONDS`; check VPN or proxy. |
| "no browser" or sign-in errors | No sign-in available | Run `az login`, or tell the user the browser tab must be clicked. |
| 400 about `response_format` or `json_object` | Model does not support JSON mode | Tell the user which deployment; pick a chat model that does, or report it. |

### 2.5 Test the pipeline agents on the model

```powershell
backend\.venv\Scripts\python.exe e2e\run_e2e.py --url http://localhost:8001
```

The last line of the run shows the audit URL of the new report, `http://localhost:8001/api/v1/reports/<id>/agent-runs`. The line `info agent modes used`
lists only the set of modes. For the detail per agent run:

```powershell
Invoke-RestMethod http://localhost:8001/api/v1/reports/<id>/agent-runs | Select-Object agent, mode, status, note, duration_ms | Format-Table -AutoSize
```

For every agent look at `mode` and `note`. **A silent fallback is the main risk**: if the model answers badly or fails, the agent falls back to the rules path and the
flow still "works" with `mode: rules` and a `note` that says why. A pass of the e2e script is therefore not enough; confirm that the agents ran in `llm` mode.

The model path of the pipeline agents has **never run against a real model** so far; it was tested only with scripted answers. Expect findings:

- A model answer that does not match the output schema is repaired once, then replaced by the rules answer. If an agent keeps falling back, read its `note`, open its file in `agents/app/agents/<agent>.py` and improve its prompt or its `clean()` logic.
- **Do not weaken the guard rails** in `clean()` to make the model look better: unknown ids, quotes that do not occur verbatim in the text, and numbers not in the quote must keep being dropped. A claim must never lose its evidence.
- Some e2e checks assume the predictable rules answers (for example the planted wrong number that must be flagged). On a model a check can fail because of wording. Decide whether the model, the prompt or the test assumption is wrong, and tell the user which. Do not just edit the test until it passes.
- Keep the rules path and the fallback. Keep `AGENT_MODE=auto` as the final setting once things work.

### 2.6 Done when

- `/health/llm` is ok, the 13 agents show `llm`, and an e2e run produced a deck with the agents in `llm` mode (list the modes you saw per agent).
- Tests still pass (48 and 26, or more if you added some).
- `agents\.env` is not tracked by git (`git status` does not list it) and contains the final settings. Set `AGENT_MODE=auto`.
- Report to the user: which agents ran in `llm`, which fell back and why, token usage per agent (the audit has it), and what you changed in prompts.

---

## Task 3: Group UI colours and fonts

Goal: the front end uses the Volkswagen Group UI colours and typography, and nothing else changes.

The complete instructions are in **`committee-report-assistant/VW_BRANDING.md`**. Read it first and follow it exactly. In short:

- The user gives you the **URL(s) of the Group UI / design system** in the chat (colours, fonts, logo). Write them into section 1 of that file. If a page needs a login you cannot use, ask the user to paste the values or a screenshot. Do not guess a colour or a font.
- Change **only token values** in the `:root` block of `committee-report-assistant/src/styles.css` and the font loading in `committee-report-assistant/index.html`. No layout, no components, no copy, no new dependencies.
- Brand fonts may need a licence or an internal font package. If the fonts are not freely hosted, ask the user how to load them. Do not copy font files from the internet.
- All commands in that file run **inside `committee-report-assistant/`**, not in the repository root.
- Check the result in the browser (all three stages, slides, charts, hover and focus states, German and English) and run `npm run build`.
- At the end fill in section 8 of `VW_BRANDING.md` (what changed, what is unknown, what the design system asks that is out of scope).

---

## Not done yet (do not start unless the user asks)

1. The front end has two modes: **Demo** (built-in sample data) and **Live** (the real backend, see `README.md`). Live was tested only with the agents in rules mode; run it against the real model (Task 2) and fix what the model changes (prompts are in `agents/app/agents/*.py`).
2. Speech input uses the browser's speech recognition, which sends audio to Google. Replace with Azure Speech inside the VW tenant before real data is used.
3. Web research is on by default for every report. It uses Foundry's web search tool and has only been tested with a stub; check on a real model that briefings, cited pages and their pictures come back. Also check the research planner (Research plan tab) and the asset analyst (Pictures and charts tab) on real documents.
4. No login and no user roles. SQLite instead of PostgreSQL; local folders instead of SharePoint, Exchange, Teams and SAP connectors; threads instead of a queue. The move to Foundry hosting comes after the local checks.
5. German wording needs a review by a native speaker.

---

## Ready-to-paste prompts

**Task 1**
```
Read COPILOT_START_HERE.md in this repository and do Task 1 (install and run everything locally). Follow the rules at the top of that file.
Check each step as described and report what you installed, what passed and what did not.
```

**Task 2**
```
Read COPILOT_START_HERE.md and do Task 2 (connect the agents to the Foundry model). Ask me for the endpoint and the deployment name before
you edit anything. I sign in with my Azure account (Azure CLI and the browser tab), not with a key. Do not commit agents/.env.
Tell me which agents ran on the model and which fell back to the rules, and why.
```

**Task 3**
```
Read COPILOT_START_HERE.md and do Task 3 (group UI colours and fonts). The group UI URL is: <PASTE URL HERE>.
Follow committee-report-assistant/VW_BRANDING.md exactly. Change only colour and font tokens and the font loading.
```
