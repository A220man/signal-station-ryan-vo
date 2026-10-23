"""Distributed agent fleet coordination: worker registration, heartbeats, and health monitoring."""
import json
import datetime
from typing import Dict, Any, List, Optional
from app.core.database import transaction, get_connection


class FleetService:
    """Manages multi-node agent worker lifecycle and coordination."""

    HEARTBEAT_INTERVAL_SECONDS = 30
    HEARTBEAT_TIMEOUT_SECONDS = 90  # 3 missed heartbeats = inactive
    DRAIN_TIMEOUT_SECONDS = 300

    @classmethod
    def register_worker(
        cls,
        worker_id: str,
        display_name: str,
        capabilities: List[str],
        max_concurrent_sessions: int,
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Register a new worker node or update existing registration."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with transaction() as conn:
            existing = conn.execute(
                "SELECT worker_id FROM workers WHERE worker_id = ?", (worker_id,)
            ).fetchone()
            if existing:
                conn.execute(
                    """UPDATE workers SET
                        display_name = ?, capabilities = ?, max_concurrent_sessions = ?,
                        metadata = ?, status = 'active', last_heartbeat_at = ?, updated_at = ?
                       WHERE worker_id = ?""",
                    (
                        display_name,
                        json.dumps(capabilities),
                        max_concurrent_sessions,
                        json.dumps(metadata),
                        now,
                        now,
                        worker_id,
                    ),
                )
            else:
                conn.execute(
                    """INSERT INTO workers (
                        worker_id, display_name, capabilities, max_concurrent_sessions,
                        metadata, status, registered_at, last_heartbeat_at, active_sessions,
                        total_sessions_handled, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 'active', ?, ?, 0, 0, ?, ?)""",
                    (
                        worker_id,
                        display_name,
                        json.dumps(capabilities),
                        max_concurrent_sessions,
                        json.dumps(metadata),
                        now,
                        now,
                        now,
                        now,
                    ),
                )
        return cls.get_worker(worker_id)

    @classmethod
    def heartbeat(
        cls,
        worker_id: str,
        active_sessions: int,
        cpu_percent: Optional[float],
        memory_mb: Optional[int],
        metadata: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Process worker heartbeat and return any assigned work or drain signals."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with transaction() as conn:
            worker = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ?", (worker_id,)
            ).fetchone()
            if not worker:
                raise ValueError(f"Worker '{worker_id}' not registered")

            # Determine new status based on current status and NEW active_sessions
            current_status = worker["status"]
            if current_status == "draining" and active_sessions == 0:
                new_status = "inactive"
            elif current_status == "draining":
                new_status = "draining"
            else:
                new_status = "active"

            # drain_requested is True if worker is still draining after this heartbeat
            # (i.e., was draining AND still has active sessions to complete)
            drain_requested = (current_status == "draining" and active_sessions > 0)

            # Update worker state
            conn.execute(
                """UPDATE workers SET
                    active_sessions = ?, last_heartbeat_at = ?, updated_at = ?,
                    cpu_percent = ?, memory_mb = ?, metadata = ?, status = ?
                WHERE worker_id = ?""",
                (
                    active_sessions,
                    now,
                    now,
                    cpu_percent,
                    memory_mb,
                    json.dumps(metadata),
                    new_status,
                    worker_id,
                ),
            )

            # In a full implementation, this would assign work from a queue
            assigned_work: List[Dict[str, Any]] = []

        return {
            "worker_id": worker_id,
            "acknowledged_at": now,
            "assigned_work": assigned_work,
            "drain_requested": drain_requested,
        }

    @classmethod
    def get_worker(cls, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get worker details by ID."""
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ?", (worker_id,)
            ).fetchone()
            if not row:
                return None
            return cls._row_to_worker(row)
        finally:
            conn.close()

    @classmethod
    def list_workers(cls) -> Dict[str, Any]:
        """List all registered workers with status counts."""
        conn = get_connection()
        try:
            rows = conn.execute("SELECT * FROM workers ORDER BY registered_at DESC").fetchall()
            workers = [cls._row_to_worker(r) for r in rows]
            return {
                "workers": workers,
                "total": len(workers),
                "active_count": sum(1 for w in workers if w["status"] == "active"),
                "draining_count": sum(1 for w in workers if w["status"] == "draining"),
                "inactive_count": sum(1 for w in workers if w["status"] == "inactive"),
            }
        finally:
            conn.close()

    @classmethod
    def request_drain(cls, worker_id: str) -> Optional[Dict[str, Any]]:
        """Request a worker to drain (finish current work, accept no new work)."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with transaction() as conn:
            worker = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ?", (worker_id,)
            ).fetchone()
            if not worker:
                return None
            conn.execute(
                "UPDATE workers SET status = 'draining', updated_at = ? WHERE worker_id = ?",
                (now, worker_id),
            )
        return cls.get_worker(worker_id)

    @classmethod
    def mark_inactive_stale(cls) -> int:
        """Mark workers as inactive if they've missed heartbeats. Returns count of workers marked inactive."""
        threshold = datetime.datetime.now(datetime.timezone.utc).timestamp() - cls.HEARTBEAT_TIMEOUT_SECONDS
        threshold_iso = datetime.datetime.fromtimestamp(threshold, tz=datetime.timezone.utc).isoformat()
        with transaction() as conn:
            cursor = conn.execute(
                """UPDATE workers SET status = 'inactive', updated_at = ?
                WHERE status = 'active' AND last_heartbeat_at < ?""",
                (datetime.datetime.now(datetime.timezone.utc).isoformat(), threshold_iso),
            )
            return cursor.rowcount

    @classmethod
    def _row_to_worker(cls, row: Any) -> Dict[str, Any]:
        return {
            "worker_id": row["worker_id"],
            "display_name": row["display_name"],
            "capabilities": json.loads(row["capabilities"] or "[]"),
            "max_concurrent_sessions": row["max_concurrent_sessions"],
            "status": row["status"],
            "registered_at": row["registered_at"],
            "last_heartbeat_at": row["last_heartbeat_at"],
            "active_sessions": row["active_sessions"],
            "total_sessions_handled": row["total_sessions_handled"],
            "cpu_percent": row["cpu_percent"],
            "memory_mb": row["memory_mb"],
            "metadata": json.loads(row["metadata"] or "{}"),
        }


def init_fleet_tables() -> None:
    """Initialize fleet coordination tables."""
    conn = get_connection()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS workers (
                worker_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                capabilities TEXT NOT NULL DEFAULT '[]',
                max_concurrent_sessions INTEGER NOT NULL DEFAULT 1,
                metadata TEXT NOT NULL DEFAULT '{}',
                status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive', 'draining')),
                registered_at TEXT NOT NULL,
                last_heartbeat_at TEXT,
                active_sessions INTEGER NOT NULL DEFAULT 0,
                total_sessions_handled INTEGER NOT NULL DEFAULT 0,
                cpu_percent REAL,
                memory_mb INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_workers_last_heartbeat ON workers(last_heartbeat_at)"
        )
        conn.commit()
    finally:
        conn.close()