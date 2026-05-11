"""CLI for the lab."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Annotated

import typer
import yaml

from .graph import build_graph
from .metrics import MetricsReport, metric_from_state, summarize_metrics, write_metrics
from .persistence import build_checkpointer
from .report import write_report
from .scenarios import load_scenarios
from .state import initial_state

app = typer.Typer(no_args_is_help=True)


@app.command("run-scenarios")
def run_scenarios(
    config: Annotated[Path, typer.Option("--config")],
    output: Annotated[Path, typer.Option("--output")],
) -> None:
    """Run all grading scenarios and write metrics JSON."""
    cfg = yaml.safe_load(config.read_text(encoding="utf-8"))
    scenarios = load_scenarios(cfg["scenarios_path"])
    checkpointer = build_checkpointer(cfg.get("checkpointer", "memory"), cfg.get("database_url"))
    graph = build_graph(checkpointer=checkpointer)

    metrics = []
    for scenario in scenarios:
        state = initial_state(scenario)
        run_config = {"configurable": {"thread_id": state["thread_id"]}}
        start = time.perf_counter()
        final_state = graph.invoke(state, config=run_config)
        latency_ms = int((time.perf_counter() - start) * 1000)
        metrics.append(
            metric_from_state(
                final_state,
                scenario.expected_route.value,
                scenario.requires_approval,
                latency_ms=latency_ms,
            )
        )
        typer.echo(
            f"  {scenario.id}: route={final_state.get('route')} "
            f"success={metrics[-1].success} latency={latency_ms}ms"
        )

    resume_success = cfg.get("checkpointer", "memory") == "sqlite"
    report = summarize_metrics(metrics, resume_success=resume_success)
    write_metrics(report, output)

    if cfg.get("report_path"):
        write_report(report, cfg["report_path"])

    typer.echo(f"\nWrote metrics to {output}")
    typer.echo(f"success_rate={report.success_rate:.2%}  scenarios={report.total_scenarios}")


@app.command("validate-metrics")
def validate_metrics(metrics: Annotated[Path, typer.Option("--metrics")]) -> None:
    """Validate metrics JSON schema for grading."""
    payload = json.loads(metrics.read_text(encoding="utf-8"))
    report = MetricsReport.model_validate(payload)
    if report.total_scenarios < 6:
        raise typer.BadParameter("Expected at least 6 scenarios")
    typer.echo(f"Metrics valid. success_rate={report.success_rate:.2%}")


@app.command("export-diagram")
def export_diagram(
    output: Annotated[Path, typer.Option("--output")] = Path("outputs/graph_diagram.md"),
) -> None:
    """Export the graph as a Mermaid diagram."""
    graph = build_graph()
    mermaid_str = graph.get_graph().draw_mermaid()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(f"```mermaid\n{mermaid_str}\n```\n", encoding="utf-8")
    typer.echo(f"Diagram written to {output}")


if __name__ == "__main__":
    app()
