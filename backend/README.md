# Backend service

FastAPI service that the front end talks to. Port 8001.

```
pip install -r requirements.txt
cp .env.example .env        # optional
uvicorn app.main:app --port 8001 --reload
pytest                      # after: pip install -r requirements-dev.txt
```

## Settings (environment or `.env`)
| Variable | Default | Meaning |
|---|---|---|
| `AGENTS_URL` | `http://localhost:8002` | Agents service |
| `AGENTS_TIMEOUT_SECONDS` | `8` | Per call |
| `CORS_ORIGINS` | `localhost:5173, 127.0.0.1:5173, localhost:4173, null` | Allowed browser origins. `null` is only for opening the built file from disk |
| `DATA_DIR` | `./data` | Where the JSON store keeps committees and reports |

## Endpoints
- `GET /health`: includes `agents: up|down`
- `GET /api/v1/agents`
- `POST /api/v1/brief/assess`: forwards to the Brief agent. 503 if agents are unreachable, 502 if an agent fails
- `GET /api/v1/committees`
- `GET /api/v1/reports`, `POST /api/v1/reports`, `GET /api/v1/reports/{id}`, `DELETE /api/v1/reports/{id}`
- `PUT /api/v1/reports/{id}/workspace`: store the whole workspace (autosave)

Interactive docs at `/docs`.

## Structure
`app/main.py` (app factory, CORS), `app/routers/` (brief, reports, system), `app/agents_client.py` (HTTP client for agents), `app/store.py` (JSON-file store with a lock; replace with a database behind the same methods), `app/seed.py` (3 committees and 3 sample reports), `app/schemas.py`.
