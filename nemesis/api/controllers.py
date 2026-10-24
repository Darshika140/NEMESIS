"""HTTP controller functions that translate ORM entities into API contracts."""

from __future__ import annotations

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from nemesis.api.models import PipelineRun, ScenarioRecord
from nemesis.api.schemas import (
    FailureSummary,
    LatestRunResponse,
    Metrics,
    RunResponse,
    ScenarioDetail,
    ScenarioResponse,
)


def run_response(run: PipelineRun) -> RunResponse:
    known_metrics = {
        key: value
        for key, value in run.metrics.items()
        if key in Metrics.model_fields
    }
    return RunResponse(
        id=run.id,
        status=run.status,
        mode=run.mode,
        created_at=run.created_at,
        completed_at=run.completed_at,
        error=run.error,
        metrics=Metrics(**known_metrics),
        failures=[
            FailureSummary(
                id=item.id,
                title=item.title,
                kind=item.kind,
                scenario=item.detail.get("scenario", item.id),
                status=item.status,
                summary=item.summary,
            )
            for item in run.scenarios
        ],
    )


def latest_run(session: Session) -> LatestRunResponse:
    run = session.scalar(
        select(PipelineRun).order_by(desc(PipelineRun.created_at), desc(PipelineRun.id)).limit(1)
    )
    return LatestRunResponse(run=run_response(run) if run else None)


def scenario_detail(session: Session, scenario_id: str) -> ScenarioResponse | None:
    record = session.get(ScenarioRecord, scenario_id)
    if record is None:
        return None
    return ScenarioResponse(
        scenario=ScenarioDetail.model_validate(record.detail)
    )
