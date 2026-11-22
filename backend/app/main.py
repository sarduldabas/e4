"""Backend for the Committee Report Assistant.

Responsibilities: serve committees and reports to the front end, store report state, and call the agents.
It contains no agent logic itself.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .agents_client import AgentsClient
from .config import Settings, load_settings
from .routers import brief, reports, system
from .store import Store


def create_app(settings: Settings | None = None, agents: AgentsClient | None = None) -> FastAPI:
    settings = settings or load_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.agents = agents or AgentsClient(settings.agents_url, settings.agents_timeout)
        app.state.store = Store(settings.data_dir)
        yield
        await app.state.agents.aclose()

    app = FastAPI(title="COE4 Backend", version="0.1.0", lifespan=lifespan,
                  description="API for the Committee Report Assistant front end.")
    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["*"], allow_headers=["*"])
    app.include_router(system.router)
    app.include_router(brief.router)
    app.include_router(reports.router)
    return app


app = create_app()
