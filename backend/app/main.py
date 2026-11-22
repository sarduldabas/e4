"""Backend for the Committee Report Assistant.

Serves committees and reports to the front end, owns the case workspace (database + file store) and runs the
orchestrator that calls the agents service. It contains no agent logic itself.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .agents_client import AgentsClient
from .config import Settings, load_settings
from .core.storage import LocalFileStore
from .db import Database
from .routers import brief, pipeline, reports, system
from .services.ctx import Blocked, Context, NotFound, StateError
from .services.jobs import Busy, JobRunner
from .services.orchestrator import Orchestrator
from .services.reports import ReportsService
from .services.runner import AgentCallFailed, AgentsRunner

log = logging.getLogger("backend")


def create_app(settings: Settings | None = None, agents: AgentsClient | None = None, runner_transport=None, inline_jobs: bool = False) -> FastAPI:
    settings = settings or load_settings()
    db = Database(settings.db_url, settings.data_dir)
    db.create_all()
    store = LocalFileStore(settings.data_dir / "files")
    runner = AgentsRunner(settings.agents_url, settings.agent_run_timeout, db, transport=runner_transport)
    jobs = JobRunner(db, workers=2, inline=inline_jobs)
    jobs.recover()
    ctx = Context.build(db, store, runner, jobs, settings)
    orchestrator = Orchestrator(ctx)
    reports_svc = ReportsService(db, on_delete=orchestrator.purge)
    reports_svc.seed()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.agents = agents or AgentsClient(settings.agents_url, settings.agents_timeout)
        yield
        await app.state.agents.aclose()
        jobs.shutdown()
        runner.close()
        db.dispose()

    app = FastAPI(title="COE4 Backend", version="0.2.0", lifespan=lifespan, description="API for the Committee Report Assistant front end.")
    app.state.orchestrator, app.state.reports, app.state.db, app.state.ctx = orchestrator, reports_svc, db, ctx
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(system.router)
    app.include_router(brief.router)
    app.include_router(reports.router)
    app.include_router(pipeline.router)

    @app.exception_handler(NotFound)
    async def _nf(_: Request, e: NotFound):
        return JSONResponse({"detail": f"not found: {e}"}, status_code=404)

    @app.exception_handler(StateError)
    async def _se(_: Request, e: StateError):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(Busy)
    async def _busy(_: Request, e: Busy):
        return JSONResponse({"detail": str(e)}, status_code=409)

    @app.exception_handler(Blocked)
    async def _bl(_: Request, e: Blocked):
        return JSONResponse({"detail": str(e), "items": e.items}, status_code=409)

    @app.exception_handler(ValueError)
    async def _ve(_: Request, e: ValueError):
        return JSONResponse({"detail": str(e)}, status_code=422)

    @app.exception_handler(AgentCallFailed)
    async def _ag(_: Request, e: AgentCallFailed):
        return JSONResponse({"detail": f"Agents service: {e}"}, status_code=503 if e.unreachable else 502)

    return app


app = create_app()
