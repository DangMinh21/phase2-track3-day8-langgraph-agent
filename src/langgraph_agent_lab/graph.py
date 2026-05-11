"""Graph construction.

Import-safe: LangGraph is imported only inside build_graph() so unit tests
that check schema/metrics can run even without LangGraph installed.
"""

from __future__ import annotations

from typing import Any

from .nodes import (
    answer_node,
    approval_node,
    ask_clarification_node,
    classify_node,
    customer_lookup_node,
    dead_letter_node,
    evaluate_node,
    finalize_node,
    intake_node,
    order_lookup_node,
    retry_or_fallback_node,
    risky_action_node,
    tool_dispatch_node,
    tool_node,
)
from .routing import (
    fan_out_to_sources,
    route_after_approval,
    route_after_classify,
    route_after_evaluate,
    route_after_retry,
)
from .state import AgentState


def build_graph(checkpointer: Any | None = None) -> Any:
    """Build and compile the LangGraph workflow.

    Graph flow:
      START → intake → classify → [conditional]
        simple       → answer → finalize → END
        tool         → tool_dispatch → [order_lookup || customer_lookup] → evaluate
        missing_info → clarify → finalize → END
        risky        → risky_action → approval → tool_dispatch → evaluate
        error        → retry → tool → evaluate → [retry loop | answer]
        max_retry    → dead_letter → finalize → END
      evaluate (success) → answer → finalize → END
      evaluate (retry)   → retry  → tool → ...
    """
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("LangGraph is required. Run: pip install -e '.[dev]'") from exc

    graph = StateGraph(AgentState)

    # Core nodes
    graph.add_node("intake", intake_node)
    graph.add_node("classify", classify_node)
    graph.add_node("answer", answer_node)
    graph.add_node("clarify", ask_clarification_node)
    graph.add_node("risky_action", risky_action_node)
    graph.add_node("approval", approval_node)
    graph.add_node("evaluate", evaluate_node)
    graph.add_node("retry", retry_or_fallback_node)
    graph.add_node("tool", tool_node)
    graph.add_node("dead_letter", dead_letter_node)
    graph.add_node("finalize", finalize_node)

    # Parallel fan-out nodes (Bonus D)
    graph.add_node("tool_dispatch", tool_dispatch_node)
    graph.add_node("order_lookup", order_lookup_node)
    graph.add_node("customer_lookup", customer_lookup_node)

    # Edges
    graph.add_edge(START, "intake")
    graph.add_edge("intake", "classify")
    graph.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "answer": "answer",
            "tool_dispatch": "tool_dispatch",
            "clarify": "clarify",
            "risky_action": "risky_action",
            "retry": "retry",
        },
    )

    # Parallel fan-out: tool_dispatch → order_lookup + customer_lookup → evaluate
    graph.add_conditional_edges(
        "tool_dispatch", fan_out_to_sources, ["order_lookup", "customer_lookup"]
    )
    graph.add_edge("order_lookup", "evaluate")
    graph.add_edge("customer_lookup", "evaluate")

    # Evaluate gate: retry loop or answer
    graph.add_conditional_edges(
        "evaluate", route_after_evaluate, {"retry": "retry", "answer": "answer"}
    )

    # Retry loop: bounded by max_attempts → dead_letter
    graph.add_conditional_edges(
        "retry", route_after_retry, {"tool": "tool", "dead_letter": "dead_letter"}
    )
    graph.add_edge("tool", "evaluate")

    # Risky path: approval → tool_dispatch (reuses parallel fan-out)
    graph.add_edge("risky_action", "approval")
    graph.add_conditional_edges(
        "approval", route_after_approval, {"tool_dispatch": "tool_dispatch", "clarify": "clarify"}
    )

    # Terminal paths → finalize → END
    graph.add_edge("answer", "finalize")
    graph.add_edge("clarify", "finalize")
    graph.add_edge("dead_letter", "finalize")
    graph.add_edge("finalize", END)

    return graph.compile(checkpointer=checkpointer)
