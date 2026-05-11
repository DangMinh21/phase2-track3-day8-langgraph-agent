"""Node functions for the LangGraph workflow."""

from __future__ import annotations

import json
import os
import re
from typing import Any

from .state import AgentState, ApprovalDecision, Route, make_event

# ---------------------------------------------------------------------------
# Classify helpers
# ---------------------------------------------------------------------------

_RISKY_KEYWORDS: list[str] = ["refund", "delete", "send", "cancel", "remove", "revoke"]
_TOOL_KEYWORDS: list[str] = ["status", "order", "lookup", "check", "track", "find", "search"]
_ERROR_KEYWORDS: list[str] = ["timeout", "fail", "failure", "error", "crash", "unavailable"]
_MISSING_INFO_PRONOUNS: list[str] = ["it", "this", "that"]

_CLASSIFY_SYSTEM_PROMPT = (
    "You are a support ticket classifier. Classify the user query into exactly one route.\n\n"
    "Routes:\n"
    "- risky: refund, delete account, cancel subscription, send email, remove data, revoke access\n"
    "- tool: lookup order, check status, track shipment, search records, find information\n"
    "- missing_info: too short/vague (< 5 words, pronouns: 'it', 'this', 'that')\n"
    "- error: timeout, failure, crash, system unavailable, cannot recover\n"
    "- simple: general question not matching above categories\n\n"
    "Return ONLY valid JSON:\n"
    '{"route": "simple|tool|missing_info|risky|error", "risk_level": "low|high", "reason": "..."}'
)


def _has_keyword(text: str, keyword: str) -> bool:
    """Return True when keyword appears as a whole word in text."""
    return bool(re.search(rf"\b{re.escape(keyword)}\b", text))


def _classify_with_keywords(query: str) -> tuple[str, str]:
    """Keyword-based fallback classifier. Returns (route, risk_level)."""
    q = query.lower()
    words = [w.strip("?!.,;:") for w in q.split()]
    # Priority 1 — risky actions
    if any(_has_keyword(q, kw) for kw in _RISKY_KEYWORDS):
        return Route.RISKY.value, "high"
    # Priority 2 — tool/lookup
    if any(_has_keyword(q, kw) for kw in _TOOL_KEYWORDS):
        return Route.TOOL.value, "low"
    # Priority 3 — missing info (short + vague pronoun)
    if len(words) < 5 and any(_has_keyword(q, p) for p in _MISSING_INFO_PRONOUNS):
        return Route.MISSING_INFO.value, "low"
    # Priority 4 — error/failure
    if any(_has_keyword(q, kw) for kw in _ERROR_KEYWORDS):
        return Route.ERROR.value, "low"
    return Route.SIMPLE.value, "low"


def _classify_with_llm(query: str) -> tuple[str, str, str]:
    """LLM-based classifier via OpenAI. Returns (route, risk_level, reason).

    Raises on any failure so the caller can fall back to keyword logic.
    """
    from openai import OpenAI  # lazy import — optional dependency

    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise ValueError("OPENAI_API_KEY not set")

    client = OpenAI(api_key=api_key)
    model = os.environ.get("CLASSIFY_MODEL", "gpt-4o-mini")

    response = client.chat.completions.create(
        model=model,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _CLASSIFY_SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        timeout=10.0,
        max_tokens=100,
    )

    raw = response.choices[0].message.content or "{}"
    data: dict[str, Any] = json.loads(raw)
    route = str(data.get("route", ""))
    Route(route)  # validate — raises ValueError if unknown enum value
    return route, str(data.get("risk_level", "low")), str(data.get("reason", ""))


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


def intake_node(state: AgentState) -> dict:
    """Normalize raw query: strip whitespace and record audit event."""
    query = state.get("query", "").strip()
    return {
        "query": query,
        "messages": [f"intake:{query[:40]}"],
        "events": [make_event("intake", "completed", "query normalized")],
    }


def classify_node(state: AgentState) -> dict:
    """Classify query via OpenAI LLM (primary) with keyword-based fallback."""
    query = state.get("query", "").strip()
    try:
        route, risk_level, _ = _classify_with_llm(query)
        method = "llm"
    except Exception:
        route, risk_level = _classify_with_keywords(query)
        method = "keyword"
    return {
        "route": route,
        "risk_level": risk_level,
        "events": [make_event("classify", "completed", f"route={route}", via=method)],
    }


def ask_clarification_node(state: AgentState) -> dict:
    """Ask for missing information rather than hallucinating."""
    query = state.get("query", "")
    question = (
        f"Your request '{query[:60]}' is missing context. "
        "Please provide more details, such as an order ID or specific action."
    )
    return {
        "pending_question": question,
        "final_answer": question,
        "events": [make_event("clarify", "completed", "clarification question sent")],
    }


def tool_dispatch_node(state: AgentState) -> dict:
    """Entry point for parallel tool dispatch — triggers fan-out via conditional edge."""
    return {
        "events": [make_event("tool_dispatch", "dispatching", "parallel lookup initiated")],
    }


def order_lookup_node(state: AgentState) -> dict:
    """Mock order-database lookup — one of two parallel sources."""
    scenario_id = state.get("scenario_id", "unknown")
    query = state.get("query", "")[:40]
    result = f"ORDER_DB: order found | scenario={scenario_id} | query='{query}' | status=delivered"
    return {
        "tool_results": [result],
        "events": [make_event("order_lookup", "completed", "order DB lookup done")],
    }


def customer_lookup_node(state: AgentState) -> dict:
    """Mock customer-database lookup — one of two parallel sources."""
    scenario_id = state.get("scenario_id", "unknown")
    result = f"CUSTOMER_DB: customer active | scenario={scenario_id} | tier=premium"
    return {
        "tool_results": [result],
        "events": [make_event("customer_lookup", "completed", "customer DB lookup done")],
    }


def tool_node(state: AgentState) -> dict:
    """Execute a single mock tool. Used as fallback during retry loops."""
    attempt = int(state.get("attempt", 0))
    scenario_id = state.get("scenario_id", "unknown")
    route = state.get("route", "")
    # Simulate transient failure for error-route scenarios on early attempts
    if route == Route.ERROR.value and attempt < 2:
        result = f"ERROR: transient failure attempt={attempt} scenario={scenario_id}"
    else:
        result = f"tool-result: scenario={scenario_id} attempt={attempt}"
    return {
        "tool_results": [result],
        "events": [make_event("tool", "completed", f"tool executed attempt={attempt}")],
    }


def risky_action_node(state: AgentState) -> dict:
    """Prepare a risky action summary for human approval."""
    query = state.get("query", "")
    action = f"Proposed action for: '{query[:80]}' — requires human approval before execution."
    return {
        "proposed_action": action,
        "events": [
            make_event("risky_action", "pending_approval", "approval required")
        ],
    }


def approval_node(state: AgentState) -> dict:
    """Human approval step. Uses real interrupt() when LANGGRAPH_INTERRUPT=true, else mock."""
    if os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true":
        from langgraph.types import interrupt  # noqa: PLC0415

        value = interrupt({
            "proposed_action": state.get("proposed_action"),
            "risk_level": state.get("risk_level"),
        })
        if isinstance(value, dict):
            decision = ApprovalDecision(**value)
        else:
            decision = ApprovalDecision(approved=bool(value))
    else:
        decision = ApprovalDecision(approved=True, comment="mock approval")

    return {
        "approval": decision.model_dump(),
        "events": [
            make_event("approval", "completed", f"approved={decision.approved}")
        ],
    }


def retry_or_fallback_node(state: AgentState) -> dict:
    """Increment attempt counter and record the retry event."""
    attempt = int(state.get("attempt", 0)) + 1
    return {
        "attempt": attempt,
        "errors": [f"transient failure logged at attempt={attempt}"],
        "events": [make_event("retry", "attempt", f"retry attempt={attempt}", attempt=attempt)],
    }


def evaluate_node(state: AgentState) -> dict:
    """Evaluate the latest tool result — the 'done?' gate for the retry loop."""
    tool_results = state.get("tool_results", [])
    latest = tool_results[-1] if tool_results else ""
    if "ERROR" in latest:
        return {
            "evaluation_result": "needs_retry",
            "events": [make_event("evaluate", "needs_retry", "tool result indicates failure")],
        }
    return {
        "evaluation_result": "success",
        "events": [make_event("evaluate", "success", "tool result satisfactory")],
    }


def answer_node(state: AgentState) -> dict:
    """Produce a final response grounded in tool results and approval context."""
    tool_results = state.get("tool_results", [])
    approval = state.get("approval")
    if tool_results and approval:
        answer = (
            f"Action approved by {approval.get('reviewer', 'reviewer')}. "
            f"Result: {tool_results[-1]}"
        )
    elif tool_results:
        answer = f"Here is what I found: {tool_results[-1]}"
    else:
        answer = "Your request has been processed successfully."
    return {
        "final_answer": answer,
        "events": [make_event("answer", "completed", "final answer generated")],
    }


def dead_letter_node(state: AgentState) -> dict:
    """Log unresolvable failures after max retries for manual review."""
    attempt = int(state.get("attempt", 0))
    scenario_id = state.get("scenario_id", "unknown")
    return {
        "final_answer": (
            f"Request could not be completed after {attempt} attempt(s). "
            f"Ticket {scenario_id} has been escalated for manual review."
        ),
        "events": [make_event("dead_letter", "escalated", f"max retries exceeded attempt={attempt}")],  # noqa: E501
    }


def finalize_node(state: AgentState) -> dict:
    """Emit final audit event and mark workflow complete."""
    route = state.get("route", "unknown")
    answer_present = bool(state.get("final_answer") or state.get("pending_question"))
    return {
        "events": [
            make_event("finalize", "completed", f"route={route} has_answer={answer_present}")
        ],
    }
