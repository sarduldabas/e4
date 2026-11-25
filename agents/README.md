# Agents service

FastAPI service that hosts the agents. Called only by the backend. Port 8002.

```
pip install -r requirements.txt
uvicorn app.main:app --port 8002 --reload
pytest        # after: pip install -r requirements-dev.txt
```

## Endpoints
- `GET /health`, `GET /health/llm` (calls the model once: checks endpoint, deployment and credentials)
- `GET /v1/agents`: the 17 agents and the mode each runs in
- `POST /v1/agents/{id}/run`: JSON in, JSON out, the same envelope for every pipeline agent: `{agent, version, mode, model, note, usage, duration_ms, output}`
- `GET /v1/agents/{id}/schema`: input and output JSON Schema of an agent
- `POST /v1/brief/assess`: the Brief agent (front end, via the backend)

## The agents (`app/agents/`)
| Agent | Tier | Job |
|---|---|---|
| `brief` | standard | scores the brief, understands topic, committee, date; hints and questions (Stage 1) |
| `template-analyst` | strong | template structure -> outline with the inputs each section needs; without a template it advises a structure |
| `document-reader` | vision | reads pages that code cannot read (scans, images, figures): text, tables, figure facts; marks what is unreadable |
| `interviewer` | strong | captures what the user says, judges coverage, asks the next question, stops when covered / user done / 12 questions |
| `source-planner` | standard | which sources to search, with which terms, per section |
| `source-screener` | small | relevance, duplicates and old versions among the hits |
| `web-search` | standard | Foundry web search tool: finds pages and facts for a query (no Bing key, no extra credentials); every page becomes a source |
| `web-researcher` | standard | findings from fetched public pages (each with a quote that must occur in the page) |
| `evidence-extractor` | standard | facts, figures, risks from one document; each with a verbatim quote and locator, checked mechanically |
| `asset-curator` | vision | which images and tables belong on which slide |
| `section-analyst` | strong | `plan`: which calculations; `write`: claims tied to evidence and calculation ids; reads raw source passages and may add verified evidence |
| `verifier` | strong | checks every claim against its evidence; a wrong number is a blocker whatever the model says |
| `red-team` | strong | sceptical reading of the whole draft: hard questions, gaps, inconsistencies |
| `storyline-architect` | strong | the story of the deck: key message per section, order, which slides carry which numbers |
| `slide-writer` | strong | one slide spec per slide: layout, KPIs, chart, table, callout, bullets tied to claims, notes |
| `slide-editor` | strong | carries out a reviewer's comment on one slide; says what it changed and what it could not do |
| `feedback-interpreter` | standard | free-text feedback -> structured changes with the re-run point |

Every agent has a **model path** and a **rules path**. With a model configured (`AGENT_MODE=auto|llm`) the model answers; its
answer is validated against the output schema (one repair attempt), and anything it cannot back up is dropped
(`clean()`: unknown ids, quotes that are not in the text, numbers that are not in the quote). If the model is down or keeps
returning unusable JSON the rules path answers, and the response says so (`mode: "rules"`, `note`). `AGENT_MODE=rules`
never calls a model. Rules answers are simple and safe, not smart: they exist for tests, demos and as a safety net.

## Brief agent (`app/agents/brief_agent.py`)
Score out of 100: topic 15, committee 10, date 8, description up to 17 (80 words), material up to 28 (6 items; only files with status `ready` plus links), sources up to 6 (5 connectors), answers 16 across three questions.
Labels: under 40 Getting started, under 70 Good basis, under 90 Strong brief, else Excellent brief.
Questions in priority order: decision, favourite, precedent, time. At most 3 are shown. A question is skipped when the text already answers it (for example "please approve ...") and listed in `already_clear`. The precedent question names the earlier report file when one was uploaded.
Wording lives in `app/agents/texts.py` (German formal Sie and English). Extraction rules (dates, committee, topic, decision) live in `app/agents/extract.py`.

## Language model (Microsoft Foundry / Azure OpenAI)

The Brief agent has two implementations behind the same endpoint:
- **LLM agent** (`app/agents/brief_llm.py`): a model reads the brief and returns topic, committee, date, how well the case is explained,
  a 2-3 line summary, up to three hints and the questions worth asking. The prompt is in `app/agents/prompts.py`.
  The score is still computed in code with the same transparent formula (`breakdown` in the response); the model supplies the inputs.
  The options of each question always come from the tool, so stored answers stay stable.
- **Rules agent** (`app/agents/brief_agent.py`): the safety net. If the model times out, errors or answers something unusable,
  the user gets the rules result and `agent.mode` is `"rules"` with `agent.note` saying why. After a failure the model is skipped for 30 s.

Setup: copy `.env.example` to `.env` in this folder and fill in `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` (the deployment name) and
**either** `AZURE_OPENAI_API_KEY` **or** `AZURE_USE_ENTRA_ID=true` (no key; sign in with your Azure account). Restart the agents service, then check the connection.

Entra ID sign-in (`AZURE_USE_ENTRA_ID=true`), as used by the colleague's chat app: the service takes the first identity it finds (environment,
managed identity, VS Code, Azure CLI, Azure PowerShell, azd) and, if there is none, opens a **browser tab** where you pick your account
(`AZURE_ENTRA_BROWSER=true`, the default). With the Azure CLI installed, run `az login` once and no tab is needed. The sign-in happens once
per start of the service, on the first model call; parallel agent calls wait for it. Opening `/health/llm` triggers it on purpose.
Your account needs a role on the Foundry / Azure OpenAI resource that allows calling models (for example *Cognitive Services OpenAI User*); a 401/403 after signing in usually means the role is missing.

```
curl http://localhost:8002/health        # mode: "llm" when the model is in use
curl http://localhost:8002/health/llm    # calls the model once: {"ok": true, "latency_ms": ...} or the error
```
`AGENT_MODE=rules` switches the model off. The key is never logged or returned by any endpoint. Identical requests are cached (128 entries in memory).
What the model sees: the brief text (first 8000 characters), file names and kinds, links, which sources are switched on, and the answers given.
File contents are not sent yet.

## Add an agent
1. Create `app/agents/<name>.py`: input and output pydantic models, a class derived from `BaseAgent` (`id`, `name`, `tier`,
   `system` prompt, `rules()`, and `clean()` for everything a model answer must prove), see `verifier.py` for a small one.
2. Add it to `AGENT_CLASSES` in `app/agents/registry.py`. The endpoint, the schema and the model/rules switch come for free.
3. Call it from the backend orchestrator through `ctx.runner.run("<id>", payload, report_id=...)`.
4. Test the rules path, and the model path with a scripted model (see `tests/test_agents.py`).

The Brief agent (`brief_llm.py`) predates this base class and has its own endpoint.
