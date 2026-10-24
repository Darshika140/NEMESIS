"""SQLAlchemy engine, session factory, and declarative base."""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Request
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool


class Base(DeclarativeBase):
    """Base class for persisted API records."""


def make_session_factory(database_url: str) -> sessionmaker[Session]:
    options: dict[str, object] = {}
    if database_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if database_url.endswith(":memory:"):
            options["poolclass"] = StaticPool
    engine = create_engine(database_url, **options)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


SessionFactory = make_session_factory


def get_session(request: Request) -> Generator[Session, None, None]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
