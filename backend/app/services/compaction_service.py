"""Event store compaction and delta retention engine for long-lived agent instances."""
import time
import json
import sqlite3
import datetime
from typing import Dict, Any, List, Optional
from app.core.database import transaction, get_connection, get_db_path

SUPERSEDED_TYPES = [
    "message.updated.1",
    "message.part.updated.1",
    "session.state.updated.1",
    "goal.progress.updated.1"
]

class CompactionService:
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """Inspect event store disk metrics, event distribution, and superseded candidates."""
        conn = get_connection()
        try:
            # Total events and payload size
            cursor = conn.execute("SELECT COUNT(*), COALESCE(SUM(LENGTH(data)), 0) FROM events;")
            total_events, total_bytes = cursor.fetchone()

            # Breakdown by event type
            cursor = conn.execute("""
                SELECT event_type, COUNT(*), COALESCE(SUM(LENGTH(data)), 0)
                FROM events
                GROUP BY event_type
                ORDER BY COUNT(*) DESC;
            """)
            events_by_type = {row[0]: row[1] for row in cursor.fetchall()}

            # Estimate superseded candidates (older sequences for snapshot types)
            placeholders = ",".join("?" for _ in SUPERSEDED_TYPES)
            cursor = conn.execute(f"""
                SELECT COUNT(*) FROM events e
                WHERE e.event_type IN ({placeholders})
                AND e.seq < (
                    SELECT MAX(e2.seq) FROM events e2
                    WHERE e2.aggregate_id = e.aggregate_id
                    AND e2.event_type = e.event_type
                );
            """, SUPERSEDED_TYPES)
            superseded_count = cursor.fetchone()[0]

            # Physical DB file size
            db_path = get_db_path()
            db_size = 0
            if db_path != ":memory:":
                import pathlib
                p = pathlib.Path(db_path)
                if p.is_file():
                    db_size = p.stat().st_size

            return {
                "total_events": total_events,
                "total_event_bytes": total_bytes,
                "events_by_type": events_by_type,
                "database_file_size_bytes": db_size,
                "superseded_candidate_count": superseded_count
            }
        finally:
            conn.close()

    @classmethod
    def compact_events(
        cls,
        session_id: Optional[str] = None,
        prune_superseded: bool = True,
        vacuum_database: bool = False
    ) -> Dict[str, Any]:
        """Prune historical superseded snapshots and reclaim database storage."""
        start_time = time.perf_counter()
        initial_stats = cls.get_stats()
        total_initial_bytes = initial_stats["total_event_bytes"]

        events_pruned = 0
        bytes_reclaimed = 0

        with transaction() as conn:
            if prune_superseded:
                placeholders = ",".join("?" for _ in SUPERSEDED_TYPES)
                
                # Identify rows to prune
                if session_id:
                    query = f"""
                        SELECT id, LENGTH(data) FROM events e
                        WHERE e.aggregate_id = ?
                        AND e.event_type IN ({placeholders})
                        AND e.seq < (
                            SELECT MAX(e2.seq) FROM events e2
                            WHERE e2.aggregate_id = e.aggregate_id
                            AND e2.event_type = e.event_type
                        );
                    """
                    params = [session_id] + SUPERSEDED_TYPES
                else:
                    query = f"""
                        SELECT id, LENGTH(data) FROM events e
                        WHERE e.event_type IN ({placeholders})
                        AND e.seq < (
                            SELECT MAX(e2.seq) FROM events e2
                            WHERE e2.aggregate_id = e.aggregate_id
                            AND e2.event_type = e.event_type
                        );
                    """
                    params = SUPERSEDED_TYPES

                cursor = conn.execute(query, params)
                candidates = cursor.fetchall()

                if candidates:
                    ids_to_delete = [row[0] for row in candidates]
                    bytes_reclaimed = sum(row[1] for row in candidates)
                    events_pruned = len(candidates)

                    # Delete in batches
                    batch_size = 500
                    for i in range(0, len(ids_to_delete), batch_size):
                        batch = ids_to_delete[i : i + batch_size]
                        q_marks = ",".join("?" for _ in batch)
                        conn.execute(f"DELETE FROM events WHERE id IN ({q_marks});", batch)

        # Optional vacuum outside transaction
        if vacuum_database and get_db_path() != ":memory:":
            vacuum_conn = get_connection()
            try:
                vacuum_conn.execute("VACUUM;")
            finally:
                vacuum_conn.close()

        duration_ms = (time.perf_counter() - start_time) * 1000.0
        ratio = (bytes_reclaimed / max(total_initial_bytes, 1)) * 100.0

        return {
            "events_scanned": initial_stats["total_events"],
            "events_pruned": events_pruned,
            "bytes_reclaimed": bytes_reclaimed,
            "compaction_ratio_pct": round(ratio, 2),
            "duration_ms": round(duration_ms, 2),
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
