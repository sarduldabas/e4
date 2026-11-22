# Agents service

FastAPI service that hosts the agents. Called only by the backend. Port 8002.

```
pip install -r requirements.txt
uvicorn app.main:app --port 8002 --reload
pytest        # after: pip install -r requirements-dev.txt
```

## Endpoints
- `GET /health`
- `GET /v1/agents`: the Brief agent (available) and the planned agents (reader, extractor, researcher, analyst, cross-checker, challenger, slide-builder)
- `POST /v1/brief/assess`: Stage 1. Input: `lang` (`de`|`en`), `text`, `overrides` (topic, committee, date, audience, template), `preset_committee`, `files` (name, kind, status), `links`, `connectors`, `answers` (question id -> option id). Output: `strength` (score, label, summary, hints, missing, breakdown), `understood`, `questions` (max 3, each with options and the current answer), `already_clear`, `can_start`.

## Brief agent (`app/agents/brief_agent.py`)
Score out of 100: topic 15, committee 10, date 8, description up to 17 (80 words), material up to 28 (6 items; only files with status `ready` plus links), sources up to 6 (5 connectors), answers 16 across three questions.
Labels: under 40 Getting started, under 70 Good basis, under 90 Strong brief, else Excellent brief.
Questions in priority order: decision, favourite, precedent, time. At most 3 are shown. A question is skipped when the text already answers it (for example "please approve ...") and listed in `already_clear`. The precedent question names the earlier report file when one was uploaded.
Wording lives in `app/agents/texts.py` (German formal Sie and English). Extraction rules (dates, committee, topic, decision) live in `app/agents/extract.py`.

## Add an agent
1. Add request/response models to `app/schemas.py` (and copy them to `backend/app/schemas.py`).
2. Create `app/agents/<name>_agent.py` with an `assess`/`run` method (see `base.py`).
3. Register an endpoint in `app/main.py` and list it in `GET /v1/agents`.
4. Add a client method in `backend/app/agents_client.py` and a route in `backend/app/routers/`.
5. Add tests next to `tests/test_brief_agent.py`.

To make an agent LLM-based, keep the same input and output models and set `agent.mode` to `llm`. Keep the rule-based version as the fallback.
