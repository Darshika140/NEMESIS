"""NEMESIS command-line interface (Generator → … → Validator)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from nemesis.agents.booking_v1 import BookingAgentV1
from nemesis.agents.booking_v2 import BookingAgentV2
from nemesis.checker import RequirementChecker
from nemesis.generator import ScenarioGenerator
from nemesis.minimizer import MinimizedScenario, Minimizer
from nemesis.runner import AgentRunner
from nemesis.tasks.booking import BOOKING_TASK
from nemesis.test_gen import RegressionTest, RegressionTestGenerator
from nemesis.validator import FixReport, FixValidator

app = typer.Typer(
    name="nemesis",
    help="NEMESIS — experimental discovery engine for AI agent failures.",
    add_completion=False,
    no_args_is_help=True,
)
console = Console()


@app.callback()
def _root() -> None:
    """NEMESIS command-line interface."""


@dataclass
class PipelineResult:
    scenarios: int = 0
    failures_discovered: int = 0
    false_success_claims: int = 0
    minimized: int = 0
    tests_generated: int = 0
    fixes_validated: int = 0
    fixes_resolved: int = 0
    regression_tests: list[RegressionTest] = field(default_factory=list)
    fix_report: FixReport | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    failure_details: list[dict[str, Any]] = field(default_factory=list)


def run_full_pipeline(
    *,
    task_name: str = "booking",
    agent_name: str = "react",
    mock_llm: bool = False,
    n_scenarios: int = 4,
) -> PipelineResult:
    """Execute Generator → Runner → Checker → Minimizer → TestGen → Validator."""
    if task_name != "booking":
        raise typer.BadParameter(f"Unsupported task {task_name!r}; use 'booking'.")
    if agent_name not in {"react", "booking_v1", "v1"}:
        raise typer.BadParameter(
            f"Unsupported agent {agent_name!r}; use 'react' (booking_v1)."
        )

    task = BOOKING_TASK
    result = PipelineResult(metadata={"mock_llm": mock_llm, "n_scenarios": n_scenarios})

    generator = ScenarioGenerator()
    runner = AgentRunner(requests_per_minute=30.0)
    checker = RequirementChecker()
    original = BookingAgentV1()
    fixed = BookingAgentV2()
    minimizer = Minimizer(agent=original, checker=checker)
    test_gen = RegressionTestGenerator()
    validator = FixValidator(runner=runner, checker=checker)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        t_gen = progress.add_task("Generating adversarial scenarios…", total=1)
        scenarios = generator.generate(task, n=n_scenarios, mock_llm=mock_llm)
        result.scenarios = len(scenarios)
        progress.update(t_gen, completed=1)

        t_run = progress.add_task("Running agent + checking requirements…", total=1)
        failures: list[tuple[Any, Any, Any]] = []
        false_success = 0
        for scenario in scenarios:
            original.reset()
            trace = runner.run(original, scenario, task, mock_llm=mock_llm)
            check = checker.check(trace, task, mock_llm=mock_llm)
            if not check.passed:
                failures.append((scenario, trace, check))
                if check.violation_type == "false_success_claim":
                    false_success += 1
        result.failures_discovered = len(failures)
        result.false_success_claims = false_success
        progress.update(t_run, completed=1)

        t_min = progress.add_task("Minimizing failing scenarios…", total=1)
        minimized: list[MinimizedScenario] = []
        for scenario, trace, _check in failures:
            minimized.append(
                minimizer.minimize(
                    scenario,
                    trace,
                    task,
                    runner,
                    agent=original,
                    mock_llm=mock_llm,
                )
            )
        result.minimized = len(minimized)
        progress.update(t_min, completed=1)

        t_tests = progress.add_task("Generating regression tests…", total=1)
        tests = test_gen.generate_all(minimized, task, mock_llm=mock_llm)
        result.tests_generated = len(tests)
        result.regression_tests = tests
        progress.update(t_tests, completed=1)

        t_val = progress.add_task("Validating fix (booking_v1 vs booking_v2)…", total=1)
        # Validate the false-success subset when present; otherwise all minimized failures.
        validate_set = [
            item
            for item in minimized
            if item.preserved_violation == "false_success_claim"
        ] or minimized
        fix_report = validator.validate(
            original,
            fixed,
            validate_set,
            task,
            mock_llm=mock_llm,
        )
        result.fix_report = fix_report
        result.fixes_validated = fix_report.total_failures
        result.fixes_resolved = fix_report.resolved_count
        validation_by_scenario = {case.scenario_id: case for case in fix_report.cases}
        tests_by_scenario = {test.scenario_id: test for test in tests}
        for item in minimized:
            trace = item.trace
            if trace is None:
                continue

            validation = validation_by_scenario.get(item.scenario_id)
            violation = item.preserved_violation or "unknown"
            original_output = (
                validation.details.get("original_final_output", trace.final_output)
                if validation
                else trace.final_output
            )
            fixed_output = (
                validation.details.get("fixed_final_output", "")
                if validation
                else ""
            )
            original_claims = _split_claims(original_output)
            fixed_claims = _split_claims(fixed_output)
            expected_claim = (
                f"Booking is not confirmed yet (status: {trace.world_state.status})."
                if violation == "false_success_claim"
                else (
                    f"Booking status: {trace.world_state.status}; "
                    f"confirmation id: "
                    f"{trace.world_state.confirmation_id or 'missing'}."
                )
            )
            result.failure_details.append(
                {
                    "id": item.scenario_id,
                    "title": violation.replace("_", " ").capitalize(),
                    "kind": violation,
                    "scenario": item.scenario_id,
                    "status": "Resolved" if validation and validation.resolved else "Unresolved",
                    "summary": trace.final_output,
                    "mechanism": (
                        f"Checker classified this trace as {violation}. "
                        f"World status: {trace.world_state.status}; "
                        f"claimed success: {trace.claimed_success}."
                    ),
                    "steps": [
                        {
                            "time": f"step {step.step_index + 1}",
                            "label": (
                                step.tool_call.get("name", "agent")
                                if step.tool_call
                                else "agent.reasoning"
                            ),
                            "result": (
                                str(step.tool_response.response)
                                if step.tool_response
                                else step.agent_thought or "No tool response"
                            ),
                            "tone": (
                                "red"
                                if step.tool_response
                                and step.tool_response.response_type in {"error", "timeout"}
                                else "amber"
                                if step.tool_response
                                and step.tool_response.response_type == "partial"
                                else "neutral"
                            ),
                        }
                        for step in trace.steps
                    ],
                    "verification": {
                        "original": {
                            "passed": validation.original_passed if validation else False,
                            "violation": validation.original_violation if validation else violation,
                            "final_output": (
                                validation.details.get("original_final_output", trace.final_output)
                                if validation
                                else trace.final_output
                            ),
                        },
                        "fixed": {
                            "passed": validation.resolved if validation else None,
                            "violation": validation.fixed_violation if validation else None,
                            "final_output": (
                                validation.details.get("fixed_final_output", "")
                                if validation
                                else ""
                            ),
                        },
                    },
                    "regression_test": (
                        tests_by_scenario[item.scenario_id].name
                        if item.scenario_id in tests_by_scenario
                        else None
                    ),
                    "claim_diff": [
                        {
                            "status": (
                                "unsupported"
                                if violation == "false_success_claim"
                                else "changed"
                            ),
                            "original": original_claims[index]
                            if index < len(original_claims)
                            else "",
                            "fixed": fixed_claims[index]
                            if index < len(fixed_claims)
                            else "",
                            "expected": expected_claim,
                        }
                        for index in range(
                            max(len(original_claims), len(fixed_claims), 1)
                        )
                    ],
                }
            )
        progress.update(t_val, completed=1)

    return result


def _split_claims(output: str) -> list[str]:
    return [
        claim.strip()
        for claim in re.split(r"(?<=[.!?])\s+|\n+", output.strip())
        if claim.strip()
    ]


def _print_summary(result: PipelineResult) -> None:
    table = Table(
        title="NEMESIS Pipeline Summary",
        show_header=True,
        header_style="bold cyan",
    )
    table.add_column("Metric", style="bold")
    table.add_column("Value", justify="right")

    table.add_row("Scenarios generated", str(result.scenarios))
    table.add_row("Failures discovered", str(result.failures_discovered))
    table.add_row("False success claims", str(result.false_success_claims))
    table.add_row("Scenarios minimized", str(result.minimized))
    table.add_row("Tests generated", str(result.tests_generated))
    table.add_row("Fixes validated", str(result.fixes_validated))
    table.add_row("Fixes resolved", str(result.fixes_resolved))

    if result.fix_report is not None:
        table.add_row(
            "Original still fails",
            str(result.fix_report.original_still_fails),
        )
        table.add_row(
            "Fixed agent passes",
            str(result.fix_report.fixed_passes),
        )

    console.print()
    console.print(table)
    console.print()

    mode = "mock_llm (offline / $0)" if result.metadata.get("mock_llm") else "live LLM"
    console.print(
        Panel.fit(
            f"[green]Pipeline complete[/green] · mode={mode}",
            title="NEMESIS",
            border_style="green",
        )
    )


@app.command("run")
def run_command(
    task: str = typer.Option("booking", "--task", help="Task id (booking)."),
    agent: str = typer.Option("react", "--agent", help="Agent family (react)."),
    full_pipeline: bool = typer.Option(
        False,
        "--full-pipeline",
        help="Run Generator → Runner → Checker → Minimizer → TestGen → Validator.",
    ),
    mock_llm: bool = typer.Option(
        False,
        "--mock-llm",
        help="Offline mode: no API calls (required for free/CI tests).",
    ),
    n_scenarios: int = typer.Option(
        4,
        "--n-scenarios",
        min=1,
        help="Number of scenarios to generate.",
    ),
) -> None:
    """Run NEMESIS discovery / validation pipeline."""
    if not full_pipeline:
        console.print(
            "[yellow]Nothing to do:[/yellow] pass [bold]--full-pipeline[/bold] "
            "to execute the end-to-end run."
        )
        raise typer.Exit(code=0)

    console.print(
        Panel.fit(
            f"[bold]task[/bold]={task}  [bold]agent[/bold]={agent}  "
            f"[bold]mock_llm[/bold]={mock_llm}",
            title="NEMESIS run",
            border_style="cyan",
        )
    )

    try:
        result = run_full_pipeline(
            task_name=task,
            agent_name=agent,
            mock_llm=mock_llm,
            n_scenarios=n_scenarios,
        )
    except Exception as exc:  # noqa: BLE001 - surface clean CLI errors
        console.print(f"[red]Pipeline failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc

    _print_summary(result)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
