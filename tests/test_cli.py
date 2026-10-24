"""CLI end-to-end tests (always --mock-llm)."""

from __future__ import annotations

import litellm
from typer.testing import CliRunner

from nemesis.agents.booking_v1 import BookingAgentV1
from nemesis.agents.booking_v2 import BookingAgentV2
from nemesis.checker import RequirementChecker
from nemesis.cli import app, run_full_pipeline
from nemesis.generator import ScenarioGenerator
from nemesis.minimizer import Minimizer
from nemesis.runner import AgentRunner
from nemesis.tasks.booking import BOOKING_TASK
from nemesis.validator import FixValidator

cli_runner = CliRunner()


def test_cli_full_pipeline_mock_llm(monkeypatch) -> None:
    def fail_if_called(*args, **kwargs) -> None:
        raise AssertionError("mock_llm mode must not make an LLM API call")

    monkeypatch.setattr(litellm, "completion", fail_if_called)
    result = cli_runner.invoke(
        app,
        [
            "run",
            "--task",
            "booking",
            "--agent",
            "react",
            "--full-pipeline",
            "--mock-llm",
            "--n-scenarios",
            "3",
        ],
    )
    assert result.exit_code == 0, result.stdout + result.stderr
    output = result.stdout
    assert "Failures discovered" in output
    assert "False success claims" in output
    assert "Tests generated" in output
    assert "Fixes validated" in output
    assert "Pipeline complete" in output


def test_cli_requires_full_pipeline_flag() -> None:
    result = cli_runner.invoke(
        app,
        ["run", "--task", "booking", "--agent", "react", "--mock-llm"],
    )
    assert result.exit_code == 0
    assert "full-pipeline" in result.stdout.lower() or "Nothing to do" in result.stdout


def test_booking_v2_does_not_false_claim_on_pending() -> None:
    generator = ScenarioGenerator()
    scenario = generator.generate(BOOKING_TASK, n=1, mock_llm=True)[0]
    runner = AgentRunner()
    checker = RequirementChecker()

    v1 = BookingAgentV1()
    v2 = BookingAgentV2()
    t1 = runner.run(v1, scenario, BOOKING_TASK, mock_llm=True)
    t2 = runner.run(v2, scenario, BOOKING_TASK, mock_llm=True)
    c1 = checker.check(t1, BOOKING_TASK, mock_llm=True)
    c2 = checker.check(t2, BOOKING_TASK, mock_llm=True)

    assert c1.violation_type == "false_success_claim"
    assert t1.claimed_success is True
    assert t2.claimed_success is False
    assert c2.violation_type != "false_success_claim"
    assert any(
        step.tool_call and step.tool_call.get("name") == "check_booking_status"
        for step in t2.steps
        if step.tool_call
    )


def test_fix_validator_resolves_false_success() -> None:
    generator = ScenarioGenerator()
    scenario = generator.generate(BOOKING_TASK, n=1, mock_llm=True)[0]
    runner = AgentRunner()
    original = BookingAgentV1()
    fixed = BookingAgentV2()

    trace = runner.run(original, scenario, BOOKING_TASK, mock_llm=True)
    minimized = Minimizer(agent=original).minimize(
        scenario, trace, BOOKING_TASK, runner, mock_llm=True
    )
    report = FixValidator(runner=runner).validate(
        original, fixed, [minimized], BOOKING_TASK, mock_llm=True
    )

    assert report.total_failures == 1
    assert report.original_still_fails == 1
    assert report.fixed_passes == 1
    assert report.resolved_count == 1
    assert report.cases[0].resolved is True


def test_run_full_pipeline_helper_mock() -> None:
    result = run_full_pipeline(
        task_name="booking",
        agent_name="react",
        mock_llm=True,
        n_scenarios=2,
    )
    assert result.scenarios == 2
    assert result.failures_discovered >= 1
    assert result.tests_generated == result.minimized
    assert result.fix_report is not None
    assert result.failure_details
    assert result.failure_details[0]["claim_diff"][0]["status"] == "unsupported"
    assert result.failure_details[0]["claim_diff"][0]["original"]
