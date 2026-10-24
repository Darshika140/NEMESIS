"""Relational records for pipeline runs and failed scenario traces."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from nemesis.api.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    mode: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    metrics: Mapped[dict[str, int]] = mapped_column(JSON, default=dict)
    scenarios: Mapped[list["ScenarioRecord"]] = relationship(
        back_populates="run",
        cascade="all, delete-orphan",
        order_by="ScenarioRecord.id",
    )


class ScenarioRecord(Base):
    __tablename__ = "scenario_records"

    id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        ForeignKey("pipeline_runs.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    run: Mapped[PipelineRun] = relationship(back_populates="scenarios")
