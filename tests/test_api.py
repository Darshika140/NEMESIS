from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from nemesis.api.main import create_app
from nemesis.api.services.inference import InferenceResult


def test_latest_run_is_null_before_any_execution() -> None:
    app = create_app(
        database_url="sqlite:///:memory:",
        cors_origins=("http://localhost:5173",),
    )

    with TestClient(app) as client:
        response = client.get("/api/latest-run")

    assert response.status_code == 200
    assert response.json() == {"run": None}


def test_post_run_persists_metrics_and_scenario_trace(monkeypatch) -> None:
    detail = {
        "id": "scn-demo-1",
        "title": "False success claim",
        "kind": "false_success_claim",
        "scenario": "scn-demo-1",
        "status": "Resolved",
        "summary": "The agent claimed success while the booking was pending.",
        "steps": [{"time": "step 1", "label": "confirm_booking", "result": "pending", "tone": "amber"}],
        "mechanism": "Pending state was incorrectly interpreted as confirmed.",
        "verification": {
            "original": {"passed": False, "final_output": "Booking confirmed"},
            "fixed": {"passed": True, "final_output": "Booking is pending"},
        },
        "claim_diff": [
            {
                "status": "unsupported",
                "original": "Booking confirmed.",
                "fixed": "Booking is pending.",
                "expected": "Booking is pending.",
            }
        ],
        "regression_test": "test_pending_is_not_confirmed",
    }

    def fake_pipeline(*, mock_llm: bool, n_scenarios: int):
        assert mock_llm is True
        assert n_scenarios == 1
        return SimpleNamespace(
            scenarios=1,
            failures_discovered=1,
            false_success_claims=1,
            minimized=1,
            tests_generated=1,
            fixes_validated=1,
            fixes_resolved=1,
            failure_details=[detail],
        )

    monkeypatch.setattr("nemesis.api.services.pipeline.run_full_pipeline", fake_pipeline)
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        created = client.post(
            "/api/run",
            json={"mode": "mock_llm", "n_scenarios": 1},
        )
        latest = client.get("/api/latest-run")
        scenario = client.get("/api/scenarios/scn-demo-1")

    assert created.status_code == 202
    run = latest.json()["run"]
    assert run["status"] == "completed"
    assert run["mode"] == "mock_llm"
    assert run["metrics"] == {
        "scenarios_generated": 1,
        "failures_discovered": 1,
        "false_success_claims": 1,
        "scenarios_minimized": 1,
        "tests_generated": 1,
        "fixes_validated": 1,
        "fixes_resolved": 1,
    }
    assert run["failures"][0]["id"] == "scn-demo-1"
    assert scenario.status_code == 200
    assert scenario.json()["scenario"]["verification"]["fixed"]["passed"] is True
    assert scenario.json()["scenario"]["claim_diff"][0]["status"] == "unsupported"


def test_scenario_endpoint_returns_structured_404() -> None:
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.get("/api/scenarios/missing")

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "scenario_not_found"


def test_run_defaults_to_live_llm_mode(monkeypatch) -> None:
    def fake_pipeline(*, mock_llm: bool, n_scenarios: int):
        assert mock_llm is False
        assert n_scenarios == 4
        return SimpleNamespace(
            scenarios=4,
            failures_discovered=0,
            false_success_claims=0,
            minimized=0,
            tests_generated=0,
            fixes_validated=0,
            fixes_resolved=0,
            failure_details=[],
        )

    monkeypatch.setattr("nemesis.api.services.pipeline.run_full_pipeline", fake_pipeline)
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        created = client.post("/api/run", json={})
        latest = client.get("/api/latest-run")

    assert created.status_code == 202
    assert latest.json()["run"]["mode"] == "live_llm"
    assert latest.json()["run"]["metrics"]["scenarios_generated"] == 4


def test_local_run_routes_pipeline_inference_to_ollama(monkeypatch) -> None:
    import litellm

    captured: dict[str, object] = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return "local inference"

    def fake_pipeline(*, mock_llm: bool, n_scenarios: int):
        from nemesis.runner import groq_completion

        assert mock_llm is False
        assert n_scenarios == 1
        groq_completion(messages=[{"role": "user", "content": "pipeline test"}])
        return SimpleNamespace(
            scenarios=1,
            failures_discovered=0,
            false_success_claims=0,
            minimized=0,
            tests_generated=0,
            fixes_validated=0,
            fixes_resolved=0,
            failure_details=[],
        )

    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(litellm, "completion", fake_completion)
    monkeypatch.setattr("nemesis.api.services.pipeline.run_full_pipeline", fake_pipeline)
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        created = client.post("/api/run", json={"mode": "local_llm", "n_scenarios": 1})
        latest = client.get("/api/latest-run")

    assert created.status_code == 202
    assert latest.json()["run"]["status"] == "completed"
    assert latest.json()["run"]["mode"] == "local_llm"
    assert captured["model"] == "ollama_chat/gemma4:e2b"
    assert captured["api_base"] == "http://127.0.0.1:11434"
    assert captured["api_key"] == "ollama"


def test_cors_allows_configured_frontend_origin() -> None:
    app = create_app(
        database_url="sqlite:///:memory:",
        cors_origins=("http://localhost:5173",),
    )

    with TestClient(app) as client:
        response = client.options(
            "/api/latest-run",
            headers={
                "Origin": "http://localhost:5173",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def test_chat_uses_injected_logs_and_validates_citation(monkeypatch) -> None:
    def fake_complete_json(*, provider, messages, temperature):
        assert provider == "ollama"
        assert "scenario scn-1 failed" in messages[1]["content"]
        return InferenceResult(
            content=(
                '{"answer":"The booking remained pending.",'
                '"evidence":[{"path":"$.run.status","quote":"pending"}],'
                '"insufficient_data":false}'
            ),
            provider="ollama",
            model="gemma4:e2b",
        )

    monkeypatch.setattr(
        "nemesis.api.services.diagnostics.complete_json",
        fake_complete_json,
    )
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "message": "Why did scenario 2 fail?",
                "execution_logs": {"scenario": "scenario scn-1 failed", "run": {"status": "pending"}},
                "provider": "ollama",
            },
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "The booking remained pending."
    assert response.json()["evidence"][0]["path"] == "$.run.status"


def test_chat_accepts_grounded_numeric_metric_citation(monkeypatch) -> None:
    monkeypatch.setattr(
        "nemesis.api.services.diagnostics.complete_json",
        lambda **_kwargs: InferenceResult(
            content=(
                '{"answer":"Three cases failed.",'
                '"evidence":[{"path":"$.run.metrics.failures_discovered","quote":"3"}],'
                '"insufficient_data":false}'
            ),
            provider="groq",
            model="openai/gpt-oss-20b",
        ),
    )
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "message": "How many cases failed?",
                "execution_logs": {"run": {"metrics": {"failures_discovered": 3}}},
                "provider": "groq",
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "Three cases failed."
    assert payload["insufficient_data"] is False
    assert payload["evidence"][0]["quote"] == "3"


def test_chat_accepts_grounded_boolean_citation(monkeypatch) -> None:
    monkeypatch.setattr(
        "nemesis.api.services.diagnostics.complete_json",
        lambda **_kwargs: InferenceResult(
            content=(
                '{"answer":"The fixed verification passed.",'
                '"evidence":[{"path":"$.selected_scenario.verification.fixed.passed","quote":"true"}],'
                '"insufficient_data":false}'
            ),
            provider="ollama",
            model="gemma4:e2b",
        ),
    )
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "message": "Did the fixed agent pass?",
                "execution_logs": {
                    "selected_scenario": {"verification": {"fixed": {"passed": True}}}
                },
                "provider": "ollama",
            },
        )

    assert response.status_code == 200
    assert response.json()["answer"] == "The fixed verification passed."

def test_chat_rejects_ungrounded_model_citation(monkeypatch) -> None:
    monkeypatch.setattr(
        "nemesis.api.services.diagnostics.complete_json",
        lambda **_kwargs: InferenceResult(
            content=(
                '{"answer":"The API key was rejected.",'
                '"evidence":[{"path":"$.run.error","quote":"invalid API key"}],'
                '"insufficient_data":false}'
            ),
            provider="groq",
            model="openai/gpt-oss-20b",
        ),
    )
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={"message": "Why did it fail?", "execution_logs": {"run": {"error": "timeout"}}},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["insufficient_data"] is True
    assert payload["evidence"] == []


def test_chat_reports_missing_groq_credential_as_structured_error(monkeypatch) -> None:
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.post(
            "/api/chat",
            json={
                "message": "Why did it fail?",
                "execution_logs": {},
                "provider": "groq",
            },
        )

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "groq_api_key_missing"


def test_heal_retries_until_red_team_approves(monkeypatch) -> None:
    outputs = iter(
        [
            InferenceResult(
                '{"proposed_instruction":"Check the booking state.","rationale":"Initial proposal"}',
                "groq",
                "openai/gpt-oss-20b",
            ),
            InferenceResult(
                '{"passed":false,"finding":"Does not forbid success claims while pending.","counterexample":"Tool returns pending but agent says confirmed."}',
                "groq",
                "openai/gpt-oss-20b",
            ),
            InferenceResult(
                '{"proposed_instruction":"Only claim a booking is confirmed after status is confirmed and a confirmation ID exists.","rationale":"Adds explicit ground-truth gate"}',
                "groq",
                "openai/gpt-oss-20b",
            ),
            InferenceResult(
                '{"passed":true,"finding":"All supplied cases require verified confirmation before success.","counterexample":null}',
                "groq",
                "openai/gpt-oss-20b",
            ),
        ]
    )
    monkeypatch.setattr(
        "nemesis.api.services.diagnostics.complete_json",
        lambda **_kwargs: next(outputs),
    )
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.post(
            "/api/heal",
            json={
                "instruction": "Book a hotel and confirm it.",
                "failure_evidence": {"status": "pending", "claimed_success": True},
                "test_cases": ["Do not claim success while pending."],
                "provider": "groq",
                "max_iterations": 2,
            },
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["verified"] is True
    assert len(payload["iterations"]) == 2
    assert payload["iterations"][0]["red_team_passed"] is False
    assert payload["iterations"][1]["red_team_passed"] is True


def test_heal_fails_closed_when_red_team_rejects_all_iterations(monkeypatch) -> None:
    outputs = iter(
        [
            InferenceResult(
                '{"proposed_instruction":"Try to be careful.","rationale":"Proposal"}',
                "ollama",
                "gemma4:e2b",
            ),
            InferenceResult(
                '{"passed":false,"finding":"The instruction is too vague.","counterexample":"A pending booking is reported confirmed."}',
                "ollama",
                "gemma4:e2b",
            ),
        ]
    )
    monkeypatch.setattr(
        "nemesis.api.services.diagnostics.complete_json",
        lambda **_kwargs: next(outputs),
    )
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.post(
            "/api/heal",
            json={
                "instruction": "Book a hotel.",
                "failure_evidence": {"status": "pending"},
                "test_cases": ["Do not claim a pending booking was confirmed."],
                "provider": "ollama",
                "max_iterations": 1,
            },
        )

    assert response.status_code == 200
    assert response.json()["verified"] is False


def test_streamed_heal_uses_distinct_groq_models_and_emits_debate_events(monkeypatch) -> None:
    calls = []

    def fake_complete_json(*, provider, messages, temperature, model=None):
        calls.append((provider, model, messages[0]["content"]))
        if "Fixer agent" in messages[0]["content"]:
            return InferenceResult(
                '{"proposed_instruction":"Only report confirmed states.","rationale":"State gate"}',
                provider,
                model,
            )
        return InferenceResult(
            '{"passed":true,"finding":"The supplied cases are addressed.","counterexample":null}',
            provider,
            model,
        )

    monkeypatch.setattr("nemesis.api.services.diagnostics.complete_json", fake_complete_json)
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.post(
            "/api/heal/stream",
            json={
                "instruction": "Book and report the result.",
                "failure_evidence": {"status": "pending"},
                "test_cases": ["Do not report pending as confirmed."],
                "provider": "groq",
                "max_iterations": 1,
            },
        )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = [
        __import__("json").loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [event["type"] for event in events] == [
        "fixer_started",
        "fixer_proposed",
        "red_team_started",
        "red_team_result",
        "complete",
    ]
    assert calls[0][1] == "openai/gpt-oss-20b"
    assert calls[1][1] == "openai/gpt-oss-120b"
    assert events[-1]["result"]["iterations"][0]["fixer_model"] == "openai/gpt-oss-20b"
    assert events[-1]["result"]["iterations"][0]["red_team_model"] == "openai/gpt-oss-120b"


def test_audit_endpoint_returns_strict_timestamped_unsupported_claims() -> None:
    app = create_app(database_url="sqlite:///:memory:")

    with TestClient(app) as client:
        response = client.post(
            "/api/audits",
            json={
                "scenario": {
                    "id": "scn-audit-1",
                    "title": "False success claim",
                    "kind": "false_success_claim",
                    "scenario": "booking state mismatch",
                    "status": "Resolved",
                    "summary": "Agent claimed success while pending.",
                    "claim_diff": [
                        {
                            "status": "unsupported",
                            "original": "Your booking is confirmed.",
                            "fixed": "Your booking is pending.",
                            "expected": "Booking state is pending.",
                        },
                        {
                            "status": "aligned",
                            "original": "I checked the booking.",
                            "fixed": "I checked the booking.",
                            "expected": "I checked the booking.",
                        },
                    ],
                },
            },
        )

    assert response.status_code == 200
    audits = response.json()["audits"]
    assert len(audits) == 1
    audit = audits[0]
    assert set(audit) == {
        "model_version",
        "timestamp",
        "isolated_claim",
        "divergence_reason",
    }
    assert audit["model_version"] == "not_recorded"
    assert audit["isolated_claim"] == "Your booking is confirmed."
    assert "pending" in audit["divergence_reason"]
