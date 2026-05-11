"""Checkpointer factory with SQLite and memory support."""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def build_checkpointer(kind: str = "memory", database_url: str | None = None) -> Any | None:
    """Return a LangGraph checkpointer instance.

    Args:
        kind: One of "memory", "sqlite", "none".
        database_url: File path for SQLite (e.g. "outputs/checkpoints.db").

    Falls back to MemorySaver if the requested backend is unavailable.
    """
    if kind == "none":
        return None

    if kind == "memory":
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()

    if kind == "sqlite":
        return _build_sqlite_checkpointer(database_url)

    warnings.warn(f"Unknown checkpointer kind '{kind}', falling back to MemorySaver.", stacklevel=2)
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


def _build_sqlite_checkpointer(database_url: str | None) -> Any:
    """Build a SqliteSaver with WAL mode. Falls back to MemorySaver on import error."""
    try:
        import sqlite3

        from langgraph.checkpoint.sqlite import SqliteSaver
    except ImportError:
        logger.warning(
            "langgraph-checkpoint-sqlite not installed. "
            "Run: pip install langgraph-checkpoint-sqlite. "
            "Falling back to MemorySaver."
        )
        from langgraph.checkpoint.memory import MemorySaver

        return MemorySaver()

    db_path = database_url or "outputs/checkpoints.db"
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()

    logger.info("SQLite checkpointer ready: %s", db_path)
    return SqliteSaver(conn=conn)
