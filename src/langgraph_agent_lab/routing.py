"""Routing functions for conditional edges."""

from __future__ import annotations

from typing import Any

from .state import AgentState, Route


def route_after_classify(state: AgentState) -> str:
    """Map classified route to the next graph node."""
    route = state.get("route", Route.SIMPLE.value)
    mapping = {
        Route.SIMPLE.value: "answer",
        Route.TOOL.value: "tool_dispatch",
        Route.MISSING_INFO.value: "clarify",
        Route.RISKY.value: "risky_action",
        Route.ERROR.value: "retry",
    }
    return mapping.get(route, "answer")


def fan_out_to_sources(state: AgentState) -> list[Any]:
    """Fan out to order_lookup and customer_lookup in parallel via Send()."""
    from langgraph.types import Send  # lazy import — keeps module import-safe

    return [
        Send("order_lookup", state),
        Send("customer_lookup", state),
    ]


def route_after_retry(state: AgentState) -> str:
    """Route to tool for retry, or dead_letter when max attempts reached."""
    if int(state.get("attempt", 0)) >= int(state.get("max_attempts", 3)):
        return "dead_letter"
    return "tool"


def route_after_evaluate(state: AgentState) -> str:
    """Route to retry when tool failed, or answer when satisfactory."""
    if state.get("evaluation_result") == "needs_retry":
        return "retry"
    return "answer"


def route_after_approval(state: AgentState) -> str:
    """Continue to tool_dispatch when approved, else ask for clarification."""
    approval = state.get("approval") or {}
    return "tool_dispatch" if approval.get("approved") else "clarify"
