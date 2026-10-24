"""FastAPI application factory and production middleware configuration."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from nemesis.api.config import settings
from nemesis.api.database import Base, make_session_factory
from nemesis.api.routes import router


def create_app(
    *,
    database_url: str | None = None,
    cors_origins: tuple[str, ...] | None = None,
) -> FastAPI:
    session_factory = make_session_factory(database_url or settings.database_url)
    engine = session_factory.kw["bind"]

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        Base.metadata.create_all(engine)
        yield

    app = FastAPI(
        title="NEMESIS API",
        version="0.1.0",
        description="Pipeline run history and agent-failure trace API.",
        lifespan=lifespan,
    )
    app.state.session_factory = session_factory
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins or settings.cors_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
    )
    app.include_router(router)
    return app


app = create_app()
