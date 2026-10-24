"""Versioned dashboard routes."""

from __future__ import annotations

import json
import logging
from queue import Queue
from threading import Thread

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from nemesis.api import controllers
from nemesis.api.database import get_session
from nemesis.api.schemas import AuditRequest, AuditTrailResponse
from nemesis.api.schemas import (
    ChatRequest,
    ChatResponse,
    HealRequest,
    HealResponse,
    LatestRunResponse,
    RunAcceptedResponse,
    RunRequest,
    ScenarioResponse,
)
from nemesis.api.services.audits import audit_claims
from nemesis.api.services.diagnostics import answer_chat, heal_instruction
from nemesis.api.services.pipeline import create_run, execute_run

router = APIRouter(prefix="/api", tags=["dashboard"])
logger = logging.getLogger(__name__)


@router.post("/chat", response_model=ChatResponse)
def post_chat(request: ChatRequest) -> ChatResponse:
    return answer_chat(request)


@router.post("/heal", response_model=HealResponse)
def post_heal(request: HealRequest) -> HealResponse:
    return heal_instruction(request)


@router.post("/heal/stream")
def post_heal_stream(request: HealRequest) -> StreamingResponse:
    """Stream completed agent turns as SSE events without fabricating progress."""

    def event_stream():
        events: Queue[dict[str, object] | None] = Queue()

        def run_review() -> None:
            try:
                result = heal_instruction(request, on_event=events.put)
                events.put({"type": "complete", "result": result.model_dump(mode="json")})
            except HTTPException as exc:
                events.put({"type": "error", "detail": exc.detail})
            except Exception:
                logger.exception("Unexpected failure in streamed agent review")
                events.put(
                    {
                        "type": "error",
                        "detail": {
                            "code": "agent_review_failed",
                            "message": "The agent review failed unexpectedly.",
                        },
                    }
                )
            finally:
                events.put(None)

        worker = Thread(target=run_review, daemon=True)
        worker.start()
        while True:
            event = events.get()
            if event is None:
                break
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/audits", response_model=AuditTrailResponse)
def post_audit(request: AuditRequest) -> AuditTrailResponse:
    return audit_claims(request)


@router.get("/latest-run", response_model=LatestRunResponse)
def get_latest_run(session: Session = Depends(get_session)) -> LatestRunResponse:
    return controllers.latest_run(session)


@router.get("/scenarios/{scenario_id}", response_model=ScenarioResponse)
def get_scenario(
    scenario_id: str,
    session: Session = Depends(get_session),
) -> ScenarioResponse:
    response = controllers.scenario_detail(session, scenario_id)
    if response is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "scenario_not_found", "message": "Scenario was not found"},
        )
    return response


@router.post(
    "/run",
    response_model=RunAcceptedResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def post_run(
    request: RunRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
    session: Session = Depends(get_session),
) -> RunAcceptedResponse:
    run = create_run(session, mode=request.mode)
    background_tasks.add_task(
        execute_run,
        http_request.app.state.session_factory,
        run.id,
        n_scenarios=request.n_scenarios,
    )
    return RunAcceptedResponse(run=controllers.run_response(run))
