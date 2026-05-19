from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import ai as ai_routes
from app.api import balances as balance_routes
from app.api import currency as currency_routes
from app.api import documents as document_routes
from app.api import flights as flight_routes
from app.api import trips as trip_routes
from app.api import webhook as webhook_routes
from app.config import get_settings
from app.database import init_db
from app.diagnostics import build_startup_report, log_startup_report

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log_startup_report("api")
    await init_db()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Yo Travel API", version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(trip_routes.router)
    app.include_router(balance_routes.router)
    app.include_router(currency_routes.router)
    app.include_router(document_routes.trip_router)
    app.include_router(document_routes.doc_router)
    app.include_router(ai_routes.router)
    app.include_router(webhook_routes.router)
    app.include_router(flight_routes.flight_router)
    app.include_router(flight_routes.status_router)

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    @app.get("/diagnostics")
    async def diagnostics():
        # Безопасный JSON: без токенов и паролей.
        return build_startup_report("api")

    return app


app = create_app()
