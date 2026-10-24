"""Integration tests for discovery (generator → runner → checker), mock only."""

from nemesis.agents.booking_v1 import BookingAgentV1
from nemesis.checker import RequirementChecker
from nemesis.generator import MUTATION_STRATEGIES, ScenarioGenerator
from nemesis.runner import AgentRunner
from nemesis.tasks.booking import BOOKING_TASK


def test_generator_produces_n_mutated_scenarios() -> None:
    generator = ScenarioGenerator()
    scenarios = generator.generate(BOOKING_TASK, n=3, mock_llm=True)

    assert len(scenarios) == 3
    strategies = [s.metadata.get("mutation_strategy") for s in scenarios]
    assert strategies == list(MUTATION_STRATEGIES[:3])
    for scenario in scenarios:
        assert scenario.tool_responses
        assert {tr.tool_name for tr in scenario.tool_responses} >= {
            "search_hotels",
            "request_booking",
            "confirm_booking",
        }


def test_mutate_rejects_unknown_strategy() -> None:
    generator = ScenarioGenerator()
    base = generator.generate(BOOKING_TASK, n=1, mock_llm=True)[0]
    try:
        generator.mutate(base, "unknown strategy", mock_llm=True)
        raised = False
    except ValueError:
        raised = True
    assert raised is True


def test_discovery_pipeline_generate_run_check() -> None:
    """Generate 3 scenarios, run booking_v1, check traces — all offline."""
    generator = ScenarioGenerator()
    runner = AgentRunner()
    checker = RequirementChecker()

    scenarios = generator.generate(BOOKING_TASK, n=3, mock_llm=True)
    assert len(scenarios) == 3

    results = []
    for scenario in scenarios:
        trace = runner.run(
            BookingAgentV1(),
            scenario,
            BOOKING_TASK,
            mock_llm=True,
        )
        result = checker.check(trace, BOOKING_TASK, mock_llm=True)
        results.append((scenario, trace, result))

        assert result.claimed_success == trace.claimed_success
        assert "trace_id" in result.details
        assert set(result.invariant_results) == {
            "confirmation_id_exists",
            "status_is_confirmed",
        }

    # partial success (and silent failure) should surface the planted agent flaw.
    false_success = [
        (scenario, result)
        for scenario, _trace, result in results
        if result.violation_type == "false_success_claim"
    ]
    assert false_success, "expected at least one false_success_claim from mutated scenarios"
    assert any(
        scenario.metadata.get("mutation_strategy") == "partial success"
        for scenario, _result in false_success
    )

    # Every mutated scenario should fail the full requirement gate.
    assert all(result.passed is False for _s, _t, result in results)
