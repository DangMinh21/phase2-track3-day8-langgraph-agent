#!/usr/bin/env python3
"""Streamlit HITL UI — Human-in-the-Loop approval for LangGraph support-ticket agent.

Run:
    LANGGRAPH_INTERRUPT=true streamlit run app/streamlit_app.py
    (omit env var for mock-approval mode — HITL UI still renders)
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any

import streamlit as st

# Ensure package importable when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

# ── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="LangGraph HITL Agent",
    page_icon="🤖",
    layout="centered",
    initial_sidebar_state="expanded",
)

INTERRUPT_ENABLED = os.getenv("LANGGRAPH_INTERRUPT", "").lower() == "true"
DB_PATH = "outputs/streamlit_checkpoints.db"

_EXAMPLE_QUERIES: list[tuple[str, str, str]] = [
    ("Simple", "🟢", "How do I reset my password?"),
    ("Tool lookup", "🔵", "Please lookup order status for order 12345"),
    ("Missing info", "🟡", "Can you fix it?"),
    ("Risky — refund", "🔴", "Refund this customer and send confirmation email"),
    ("Risky — delete", "🔴", "Delete customer account after support verification"),
    ("Error / retry", "⚫", "Timeout failure while processing request"),
]

# ── Session state defaults ─────────────────────────────────────────────────
_DEFAULTS: dict[str, Any] = {
    "stage": "input",          # input | awaiting_approval | complete
    "thread_id": None,
    "partial_state": None,
    "final_result": None,
    "prefill": "",
    "query": "",
}
for _k, _v in _DEFAULTS.items():
    st.session_state.setdefault(_k, _v)


# ── Cached graph (one instance per Streamlit server process) ───────────────
@st.cache_resource
def load_graph() -> Any:
    from langgraph_agent_lab.graph import build_graph
    from langgraph_agent_lab.persistence import build_checkpointer

    checkpointer = build_checkpointer("sqlite", DB_PATH)
    return build_graph(checkpointer=checkpointer)


# ── Core logic ─────────────────────────────────────────────────────────────
def _run_initial(query: str, thread_id: str) -> None:
    """Submit a new query to the graph. Detects interrupt after invoke."""
    from langgraph_agent_lab.state import Route, Scenario, initial_state

    graph = load_graph()
    config: dict[str, Any] = {"configurable": {"thread_id": thread_id}}

    scenario = Scenario(id=thread_id, query=query, expected_route=Route.SIMPLE)
    state = initial_state(scenario)
    state["thread_id"] = thread_id

    result = graph.invoke(state, config=config)

    # Detect interrupt: graph.get_state().next is non-empty when paused
    snapshot = graph.get_state(config)

    if snapshot.next:
        # Graph paused at interrupt() inside approval_node
        st.session_state.stage = "awaiting_approval"
        st.session_state.thread_id = thread_id
        st.session_state.partial_state = result
    else:
        st.session_state.stage = "complete"
        st.session_state.thread_id = thread_id
        st.session_state.final_result = result


def _resume_graph(approved: bool, reviewer: str, comment: str) -> None:
    """Resume the interrupted graph with human decision."""
    from langgraph.types import Command

    graph = load_graph()
    config: dict[str, Any] = {"configurable": {"thread_id": st.session_state.thread_id}}

    decision = {"approved": approved, "reviewer": reviewer, "comment": comment}
    result = graph.invoke(Command(resume=decision), config=config)

    st.session_state.stage = "complete"
    st.session_state.final_result = result


def _reset() -> None:
    for k, v in _DEFAULTS.items():
        st.session_state[k] = v


# ── Sidebar ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ Configuration")

    if INTERRUPT_ENABLED:
        st.success("HITL **enabled** — real `interrupt()` active")
    else:
        st.warning("HITL **mock mode** — set `LANGGRAPH_INTERRUPT=true` for real HITL")

    st.divider()
    st.subheader("📋 Example queries")
    for label, icon, q in _EXAMPLE_QUERIES:
        if st.button(f"{icon} {label}", key=f"ex_{label}", use_container_width=True):
            _reset()
            st.session_state.prefill = q
            st.rerun()

    st.divider()
    st.caption("LangGraph 1.x · SQLite persistence · gpt-4o-mini classify")


# ── Main header ────────────────────────────────────────────────────────────
st.title("🤖 LangGraph Support Ticket Agent")
st.caption("Submit a support ticket — risky actions require human approval before execution.")
st.divider()

# ═══════════════════════════════════════════════════════════════════════════
# STAGE: input
# ═══════════════════════════════════════════════════════════════════════════
if st.session_state.stage == "input":
    with st.form("ticket_form", clear_on_submit=False):
        query = st.text_area(
            "Support ticket",
            value=st.session_state.prefill,
            placeholder="e.g. Refund this customer and send confirmation email",
            height=130,
            help="Risky queries (refund, delete, cancel…) will trigger the approval flow.",
        )
        submitted = st.form_submit_button("▶ Submit ticket", type="primary", use_container_width=True)

    if submitted:
        q = query.strip()
        if not q:
            st.warning("Please enter a query before submitting.")
        else:
            thread_id = f"ui-{int(time.time() * 1000)}"
            st.session_state.query = q
            st.session_state.prefill = q
            with st.spinner("Classifying and processing…"):
                _run_initial(q, thread_id)
            st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# STAGE: awaiting_approval
# ═══════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "awaiting_approval":
    partial: dict[str, Any] = st.session_state.partial_state or {}

    st.subheader("⚠️ Human Approval Required")

    # Context cards
    col_risk, col_route = st.columns(2)
    risk = partial.get("risk_level", "high")
    risk_icon = "🔴" if risk == "high" else "🟡"
    with col_risk:
        st.metric("Risk level", f"{risk_icon} {risk.upper()}")
    with col_route:
        st.metric("Route", partial.get("route", "risky").upper())

    st.info(f"**Query:** {partial.get('query', '—')}")

    # Proposed action box
    action = partial.get("proposed_action") or "No proposed action available."
    st.markdown("**Proposed action:**")
    st.code(action, language=None)

    # Audit trail so far
    with st.expander("📜 Audit events so far", expanded=False):
        for ev in partial.get("events", []):
            st.text(f"[{ev.get('node', '?'):<18}] {ev.get('event_type', '?'):<18} — {ev.get('message', '')}")

    st.divider()

    # Decision form
    with st.form("approval_form"):
        reviewer = st.text_input("Reviewer name", value="human-reviewer")
        comment = st.text_input("Comment (optional)", placeholder="Reason for decision…")
        col_a, col_r = st.columns(2)
        with col_a:
            approve_btn = st.form_submit_button(
                "✅ Approve", type="primary", use_container_width=True
            )
        with col_r:
            reject_btn = st.form_submit_button(
                "❌ Reject", type="secondary", use_container_width=True
            )

    if approve_btn:
        with st.spinner("Resuming graph with approval…"):
            _resume_graph(approved=True, reviewer=reviewer, comment=comment)
        st.rerun()

    if reject_btn:
        with st.spinner("Resuming graph with rejection…"):
            _resume_graph(
                approved=False,
                reviewer=reviewer,
                comment=comment or "Rejected by reviewer",
            )
        st.rerun()

# ═══════════════════════════════════════════════════════════════════════════
# STAGE: complete
# ═══════════════════════════════════════════════════════════════════════════
elif st.session_state.stage == "complete":
    result: dict[str, Any] = st.session_state.final_result or {}
    events: list[dict[str, Any]] = result.get("events", [])
    retries = sum(1 for e in events if e.get("node") == "retry")

    st.subheader("✅ Ticket Processed")

    # Summary metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Route", result.get("route", "—").upper())
    with c2:
        st.metric("Nodes", len(events))
    with c3:
        st.metric("Retries", retries)
    with c4:
        approval = result.get("approval") or {}
        if approval:
            approved = approval.get("approved", False)
            st.metric("Approval", "✅ Yes" if approved else "❌ No")
        else:
            st.metric("Approval", "—")

    st.divider()

    # Final answer
    final_answer = result.get("final_answer")
    pending = result.get("pending_question")

    if final_answer:
        if (result.get("approval") or {}).get("approved") is False:
            st.warning(f"**Rejected:** {final_answer}")
        else:
            st.success(f"**Answer:** {final_answer}")
    elif pending:
        st.info(f"**Clarification needed:** {pending}")

    # Approval badge
    if approval:
        reviewer_name = approval.get("reviewer", "unknown")
        comment_text = approval.get("comment", "")
        badge = "✅ Approved" if approval.get("approved") else "❌ Rejected"
        st.caption(f"Decision: {badge} by **{reviewer_name}**" + (f" — _{comment_text}_" if comment_text else ""))

    # Tool results
    tool_results = result.get("tool_results", [])
    if tool_results:
        with st.expander(f"🔧 Tool results ({len(tool_results)} sources)", expanded=True):
            for tr in tool_results:
                st.code(tr, language=None)

    # Full audit log
    with st.expander("📜 Full audit log", expanded=False):
        for ev in events:
            node = ev.get("node", "?")
            etype = ev.get("event_type", "?")
            msg = ev.get("message", "")
            st.text(f"[{node:<18}] {etype:<18} — {msg}")

    # Errors
    if result.get("errors"):
        with st.expander("⚠️ Errors", expanded=False):
            for err in result["errors"]:
                st.text(err)

    st.divider()
    if st.button("🔄 Submit another ticket", use_container_width=True, type="primary"):
        _reset()
        st.rerun()
