"""
Workflow checkpointing utilities.

Uses a SQLite-backed LangGraph checkpointer when available so interrupts
can be resumed after app restarts. Falls back to in-memory checkpoints.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

from langgraph.checkpoint.memory import MemorySaver


BASE_DIR = Path(__file__).parent.parent
CHECKPOINT_DIR = BASE_DIR / "outbox" / "checkpoints"
CHECKPOINT_DB = CHECKPOINT_DIR / "langgraph_checkpoints.sqlite"

_checkpoint_conn: Optional[sqlite3.Connection] = None
_checkpoint_saver: Optional[Any] = None


def get_checkpoint_db_path() -> Path:
    """Return the SQLite file path used for workflow checkpoints."""
    return CHECKPOINT_DB


def get_checkpointer() -> Any:
    """
    Return a reusable workflow checkpointer.

    Prefers SQLite persistence for production durability. If unavailable,
    falls back to in-memory checkpoints.
    """
    global _checkpoint_conn, _checkpoint_saver

    if _checkpoint_saver is not None:
        return _checkpoint_saver

    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        _checkpoint_conn = sqlite3.connect(str(CHECKPOINT_DB), check_same_thread=False)
        saver = SqliteSaver(_checkpoint_conn)
        saver.setup()
        _checkpoint_saver = saver
        return _checkpoint_saver
    except Exception as e:
        print(f"[WARN] SQLite checkpointer unavailable, using MemorySaver: {e}")
        _checkpoint_saver = MemorySaver()
        return _checkpoint_saver


def reset_checkpointer() -> None:
    """Reset cached checkpointer/connection (mainly for tests)."""
    global _checkpoint_conn, _checkpoint_saver
    try:
        if _checkpoint_conn is not None:
            _checkpoint_conn.close()
    except Exception:
        pass
    _checkpoint_conn = None
    _checkpoint_saver = None

