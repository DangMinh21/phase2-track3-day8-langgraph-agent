#!/usr/bin/env python3
"""Demo: SQLite persistence survives a simulated process restart.

Steps:
  1. Run S04_risky to completion with SQLite checkpointer (thread_id fixed)
  2. Discard the graph instance (simulate process crash)
  3. Create a fresh graph + checkpointer with the SAME SQLite file
  4. Recover state via get_state() — proves durability across restarts
  5. Walk state history — shows all intermediate checkpoints
  6. Write evidence to outputs/crash_resume_evidence.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.scenarios import load_scenarios
from langgraph_agent_lab.state import initial_state

THREAD_ID = "demo-crash-resume-001"
DB_PATH = "outputs/demo_crash_checkpoints.db"
EVIDENCE_PATH = "outputs/crash_resume_evidence.txt"


def main() -> bool:
    lines: list[str] = ["=" * 60, "CRASH-RESUME DEMO — SQLite Persistence", "=" * 60, ""]
    config = {"configurable": {"thread_id": THREAD_ID}}

    # ── Step 1: First run (pre-crash) ────────────────────────────
    lines.append("STEP 1: First run (simulates pre-crash execution)")
    lines.append("-" * 40)

    checkpointer1 = build_checkpointer("sqlite", DB_PATH)
    graph1 = build_graph(checkpointer=checkpointer1)

    scenarios = load_scenarios("data/sample/scenarios.jsonl")
    scenario = next(s for s in scenarios if s.id == "S04_risky")
    state = initial_state(scenario)
    state["thread_id"] = THREAD_ID

    result = graph1.invoke(state, config=config)
    events1 = [e.get("node") for e in result.get("events", [])]

    lines.append(f"  thread_id    : {THREAD_ID}")
    lines.append(f"  route        : {result.get('route')}")
    lines.append(f"  approval     : {result.get('approval', {}).get('approved')}")
    lines.append(f"  final_answer : {str(result.get('final_answer', ''))[:80]}")
    lines.append(f"  nodes visited: {events1}")
    lines.append(f"  checkpoints  : {DB_PATH}")
    lines.append("")

    # ── Step 2: Simulate crash ────────────────────────────────────
    lines.append("STEP 2: Simulated crash — discarding graph instance")
    lines.append("-" * 40)
    del graph1
    del checkpointer1
    lines.append("  [OK] Old graph instance discarded (process would restart here)")
    lines.append("")

    # ── Step 3: New process — recover from SQLite ─────────────────
    lines.append("STEP 3: Recovery — new graph with SAME SQLite file")
    lines.append("-" * 40)

    checkpointer2 = build_checkpointer("sqlite", DB_PATH)
    graph2 = build_graph(checkpointer=checkpointer2)

    snapshot = graph2.get_state(config)

    if not (snapshot and snapshot.values):
        lines.append("  [FAIL] No checkpoint found — recovery failed")
        _write_evidence(lines)
        return False

    recovered = snapshot.values
    lines.append(f"  route        : {recovered.get('route')}")
    lines.append(f"  approval     : {recovered.get('approval', {}).get('approved')}")
    lines.append(f"  final_answer : {str(recovered.get('final_answer', ''))[:80]}")
    lines.append(f"  match route  : {recovered.get('route') == result.get('route')}")
    lines.append("  [OK] State successfully recovered from SQLite checkpoint!")
    lines.append("")

    # ── Step 4: State history ────────────────────────────────────
    lines.append("STEP 4: State history — intermediate checkpoints")
    lines.append("-" * 40)
    history = list(graph2.get_state_history(config))
    lines.append(f"  Total checkpoints saved: {len(history)}")
    lines.append("")

    for i, snap in enumerate(history):
        nodes = [e.get("node") for e in snap.values.get("events", [])]
        last = nodes[-1] if nodes else "—"
        attempt = snap.values.get("attempt", 0)
        lines.append(f"  [{i:02d}] last_node={last:<16} attempt={attempt}  nodes_so_far={len(nodes)}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("RESULT: PASS — SQLite persistence survives simulated restart")
    lines.append("=" * 60)

    _write_evidence(lines)
    return True


def _write_evidence(lines: list[str]) -> None:
    text = "\n".join(lines)
    Path(EVIDENCE_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(EVIDENCE_PATH).write_text(text, encoding="utf-8")
    print(text)
    print(f"\nEvidence written → {EVIDENCE_PATH}")


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
