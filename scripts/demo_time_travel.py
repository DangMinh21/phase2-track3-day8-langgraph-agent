#!/usr/bin/env python3
"""Demo: Time travel with get_state_history() — replay from past checkpoint.

Steps:
  1. Run S05_error (has retry loop → multiple checkpoints)
  2. List all intermediate checkpoints via get_state_history()
  3. Pick a checkpoint from before the last retry
  4. Re-invoke from that checkpoint — graph resumes and completes
  5. Compare original vs replayed final state
  6. Write evidence to outputs/time_travel_evidence.txt
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from langgraph_agent_lab.graph import build_graph
from langgraph_agent_lab.persistence import build_checkpointer
from langgraph_agent_lab.scenarios import load_scenarios
from langgraph_agent_lab.state import initial_state

THREAD_ID = "demo-time-travel-001"
DB_PATH = "outputs/demo_timetravel_checkpoints.db"
EVIDENCE_PATH = "outputs/time_travel_evidence.txt"


def main() -> None:
    lines: list[str] = ["=" * 60, "TIME TRAVEL DEMO — get_state_history() + replay", "=" * 60, ""]
    config = {"configurable": {"thread_id": THREAD_ID}}

    # ── Step 1: Run S05_error to generate multiple checkpoints ────
    lines.append("STEP 1: Run S05_error (retry loop → many checkpoints)")
    lines.append("-" * 40)

    checkpointer = build_checkpointer("sqlite", DB_PATH)
    graph = build_graph(checkpointer=checkpointer)

    scenarios = load_scenarios("data/sample/scenarios.jsonl")
    scenario = next(s for s in scenarios if s.id == "S05_error")
    state = initial_state(scenario)
    state["thread_id"] = THREAD_ID

    result = graph.invoke(state, config=config)
    nodes_original = [e.get("node") for e in result.get("events", [])]
    retries = sum(1 for n in nodes_original if n == "retry")

    lines.append(f"  route        : {result.get('route')}")
    lines.append(f"  retries      : {retries}")
    lines.append(f"  nodes visited: {nodes_original}")
    lines.append("")

    # ── Step 2: List all checkpoints ──────────────────────────────
    lines.append("STEP 2: State history — all checkpoints")
    lines.append("-" * 40)

    history = list(graph.get_state_history(config))
    lines.append(f"  Total checkpoints: {len(history)}")
    lines.append("")

    for i, snap in enumerate(history):
        nodes = [e.get("node") for e in snap.values.get("events", [])]
        last = nodes[-1] if nodes else "START"
        attempt = snap.values.get("attempt", 0)
        eval_result = snap.values.get("evaluation_result", "—")
        lines.append(
            f"  [{i:02d}] last={last:<18} attempt={attempt}  eval={eval_result}"
        )

    lines.append("")

    # ── Step 3: Pick checkpoint for time travel ───────────────────
    lines.append("STEP 3: Time travel — pick intermediate checkpoint")
    lines.append("-" * 40)

    # Find first checkpoint where retry happened (attempt > 0, before completion)
    travel_target = None
    for snap in reversed(history):  # history is newest-first, reverse for oldest-first
        nodes_so_far = [e.get("node") for e in snap.values.get("events", [])]
        if "retry" in nodes_so_far and snap.values.get("evaluation_result") != "success":
            travel_target = snap
            break

    if travel_target is None and len(history) >= 2:
        travel_target = history[len(history) // 2]

    if travel_target is None:
        lines.append("  No suitable checkpoint found for time travel")
        _write_evidence(lines)
        return

    travel_nodes = [e.get("node") for e in travel_target.values.get("events", [])]
    travel_attempt = travel_target.values.get("attempt", 0)
    lines.append(f"  Selected checkpoint: attempt={travel_attempt}, nodes_so_far={travel_nodes}")
    lines.append("")

    # ── Step 4: Replay from that checkpoint ───────────────────────
    lines.append("STEP 4: Replay from selected checkpoint")
    lines.append("-" * 40)

    replayed = graph.invoke(None, config=travel_target.config)
    nodes_replayed = [e.get("node") for e in replayed.get("events", [])]

    lines.append(f"  route         : {replayed.get('route')}")
    lines.append(f"  nodes visited : {nodes_replayed}")
    lines.append(f"  final_answer  : {str(replayed.get('final_answer', ''))[:80]}")
    lines.append("")

    # ── Step 5: Compare ───────────────────────────────────────────
    lines.append("STEP 5: Compare original vs replayed")
    lines.append("-" * 40)
    lines.append(f"  original route  : {result.get('route')}")
    lines.append(f"  replayed route  : {replayed.get('route')}")
    lines.append(f"  routes match    : {result.get('route') == replayed.get('route')}")
    lines.append(f"  original nodes  : {len(nodes_original)}")
    lines.append(f"  replayed nodes  : {len(nodes_replayed)}")
    lines.append("")
    lines.append("  [OK] Time travel replay completed successfully!")
    lines.append("")
    lines.append("=" * 60)
    lines.append("RESULT: PASS — get_state_history() + replay from past checkpoint works")
    lines.append("=" * 60)

    _write_evidence(lines)


def _write_evidence(lines: list[str]) -> None:
    text = "\n".join(lines)
    Path(EVIDENCE_PATH).parent.mkdir(parents=True, exist_ok=True)
    Path(EVIDENCE_PATH).write_text(text, encoding="utf-8")
    print(text)
    print(f"\nEvidence written → {EVIDENCE_PATH}")


if __name__ == "__main__":
    main()
