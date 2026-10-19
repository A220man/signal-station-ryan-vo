"""Tests for SQLite event log compaction and space reclamation."""
import pytest
from app.core.database import transaction, get_connection
from app.services.compaction_service import CompactionService
from app.services.session_service import SessionService

def test_event_compaction_pruning():
    # Create test session
    sess = SessionService.create_session("Compaction Test Session")
    session_id = sess["id"]

    # Insert multiple superseded snapshot events for the same aggregate
    with transaction() as conn:
        for seq in range(1, 11):
            conn.execute(
                """
                INSERT INTO events (id, aggregate_id, seq, event_type, data, created_at)
                VALUES (?, ?, ?, 'message.updated.1', ?, '2026-10-18T00:00:00Z');
                """,
                (f"evt_msg_{seq}", session_id, seq, f'{{"step": {seq}, "payload": "{'x' * 500}"}}')
            )

    stats_before = CompactionService.get_stats()
    assert stats_before["superseded_candidate_count"] >= 9

    # Execute compaction
    result = CompactionService.compact_events(session_id=session_id, prune_superseded=True)
    assert result["events_pruned"] == 9
    assert result["bytes_reclaimed"] > 0
    assert result["compaction_ratio_pct"] > 0

    # Ensure only the latest sequence (seq=10) remains for message.updated.1
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT seq FROM events WHERE aggregate_id = ? AND event_type = 'message.updated.1';",
            (session_id,)
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == 10
    finally:
        conn.close()
