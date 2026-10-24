"""Pipeline execution and persistence orchestration."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy.orm import Session, sessionmaker

from nemesis.api.models import PipelineRun, ScenarioRecord
from nemesis.cli import run_full_pipeline
from nemesis.runner import use_inference_provider

logger = logging.getLogger(__name__)


def create_run(session: Session, *, mode: str) -> PipelineRun:
    run = PipelineRun(
        id=str(uuid4()),
        status="queued",
        mode=mode,
        metrics={},
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    return run


def execute_run(
    session_factory: sessionmaker[Session],
    run_id: str,
    *,
    n_scenarios: int,
) -> None:
    """Execute one queued pipeline and save its summary and scenario traces."""
    with session_factory() as session:
        run = session.get(PipelineRun, run_id)
        if run is None:
            logger.error("Queued pipeline run %s no longer exists", run_id)
            return
        run.status = "running"
        session.commit()
        mode = run.mode

    try:
        provider = "ollama" if mode == "local_llm" else "groq"
        with use_inference_provider(provider):
            result = run_full_pipeline(
                mock_llm=(mode == "mock_llm"),
                n_scenarios=n_scenarios,
            )
        metrics = {
            "scenarios_generated": result.scenarios,
            "failures_discovered": result.failures_discovered,
            "false_success_claims": result.false_success_claims,
            "scenarios_minimized": result.minimized,
            "tests_generated": result.tests_generated,
            "fixes_validated": result.fixes_validated,
            "fixes_resolved": result.fixes_resolved,
        }
        failure_details = result.failure_details
        status = "completed"
        error = None
    except Exception:
        logger.exception("Pipeline run %s failed", run_id)
        metrics = {}
        failure_details = []
        status = "failed"
        error = "Pipeline execution failed. Check the API server logs for details."

    with session_factory() as session:
        run = session.get(PipelineRun, run_id)
        if run is None:
            logger.error("Pipeline run %s disappeared before completion", run_id)
            return
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        run.metrics = metrics
        run.error = error
        run.scenarios.clear()
        for detail in failure_details:
            run.scenarios.append(
                ScenarioRecord(
                    id=detail["id"],
                    title=detail["title"],
                    kind=detail["kind"],
                    status=detail["status"],
                    summary=detail["summary"],
                    detail=detail,
                )
            )
        session.commit()
