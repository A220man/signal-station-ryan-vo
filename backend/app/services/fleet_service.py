
"""Distributed agent fleet coordination: worker registration, heartbeats, and health monitoring."""
import json
import datetime
import uuid
from typing import Dict, Any, List, Optional
from app.core.database import transaction, get_connection, get_db_path


class FleetService:
    """Manages multi-node agent worker lifecycle and coordination."""

    HEARTBEAT_INTERVAL_SECONDS = 30
    HEARTBEAT_TIMEOUT_SECONDS = 90  # 3 missed heartbeats = inactive
    DRAIN_TIMEOUT_SECONDS = 300

    @classmethod
    def _get_conn(cls):
        """Get a database connection with proper close_after flag for in-memory DB."""
        conn = get_connection()
        close_after = get_db_path() != ":memory:"
        return conn, close_after

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

            # Assign work from queue to worker (work stealing)
            assigned_work: List[Dict[str, Any]] = []
            available_slots = worker["max_concurrent_sessions"] - active_sessions
            if available_slots > 0 and new_status == "active":
                rows = conn.execute(
                    """SELECT * FROM work_queue
                    WHERE status = 'pending'
                    ORDER BY priority DESC, created_at ASC
                    LIMIT ?""",
                    (available_slots,),
                ).fetchall()
                for row in rows:
                    work_id = row["id"]
                    conn.execute(
                        """UPDATE work_queue SET
                            status = 'assigned', assigned_worker_id = ?, assigned_at = ?
                        WHERE id = ?""",
                        (worker_id, now, work_id),
                    )
                    conn.execute(
                        "UPDATE workers SET active_sessions = active_sessions + 1, total_sessions_handled = total_sessions_handled + 1 WHERE worker_id = ?",
                        (worker_id,),
                    )
                    assigned_work.append(cls._row_to_work_item(row))

        return {
            "worker_id": worker_id,
            "acknowledged_at": now,
            "assigned_work": assigned_work,
            "drain_requested": drain_requested,
        }

    @classmethod
    def get_worker(cls, worker_id: str) -> Optional[Dict[str, Any]]:
        """Get worker details by ID."""
        conn, close_after = cls._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ?", (worker_id,)
            ).fetchone()
            if not row:
                return None
            return cls._row_to_worker(row)
        finally:
            if close_after:
                conn.close()

    @classmethod
    def list_workers(cls) -> Dict[str, Any]:
        """List all registered workers with status counts."""
        conn, close_after = cls._get_conn()
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
            if close_after:
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
    def enqueue_work(
        cls,
        session_id: str,
        task_type: str,
        payload: Dict[str, Any],
        priority: int = 0,
    ) -> Dict[str, Any]:
        """Add a work item to the queue for a session."""
        work_id = f"wrk_{uuid.uuid4().hex[:12]}"
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with transaction() as conn:
            conn.execute(
                """INSERT INTO work_queue (
                    id, session_id, task_type, payload, priority, status, created_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?)""",
                (
                    work_id,
                    session_id,
                    task_type,
                    json.dumps(payload),
                    priority,
                    now,
                ),
            )
        return cls.get_work_item(work_id)

    @classmethod
    def get_work_item(cls, work_id: str) -> Optional[Dict[str, Any]]:
        """Get a work item by ID."""
        conn, close_after = cls._get_conn()
        try:
            row = conn.execute(
                "SELECT * FROM work_queue WHERE id = ?", (work_id,)
            ).fetchone()
            if not row:
                return None
            return cls._row_to_work_item(row)
        finally:
            if close_after:
                conn.close()

    @classmethod
    def list_pending_work(cls, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """List pending work items, optionally filtered by session."""
        conn, close_after = cls._get_conn()
        try:
            if session_id:
                rows = conn.execute(
                    "SELECT * FROM work_queue WHERE status = 'pending' AND session_id = ? ORDER BY priority DESC, created_at ASC",
                    (session_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM work_queue WHERE status = 'pending' ORDER BY priority DESC, created_at ASC"
                ).fetchall()
            return [cls._row_to_work_item(r) for r in rows]
        finally:
            if close_after:
                conn.close()

    @classmethod
    def assign_work_to_worker(cls, worker_id: str, work_id: str) -> Optional[Dict[str, Any]]:
        """Assign a specific work item to a worker."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with transaction() as conn:
            # Verify worker exists and is active
            worker = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ? AND status = 'active'", (worker_id,)
            ).fetchone()
            if not worker:
                return None

            # Check worker capacity
            if worker["active_sessions"] >= worker["max_concurrent_sessions"]:
                return None

            # Verify work item is pending
            work = conn.execute(
                "SELECT * FROM work_queue WHERE id = ? AND status = 'pending'", (work_id,)
            ).fetchone()
            if not work:
                return None

            # Assign work
            conn.execute(
                """UPDATE work_queue SET
                    status = 'assigned', assigned_worker_id = ?, assigned_at = ?
                WHERE id = ?""",
                (worker_id, now, work_id),
            )

            # Increment worker's active sessions
            conn.execute(
                "UPDATE workers SET active_sessions = active_sessions + 1, total_sessions_handled = total_sessions_handled + 1 WHERE worker_id = ?",
                (worker_id,),
            )

        return cls.get_work_item(work_id)

    @classmethod
    def steal_work(cls, worker_id: str, max_items: int = 1) -> List[Dict[str, Any]]:
        """Allow a worker to steal pending work (work stealing pattern)."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        stolen = []

        with transaction() as conn:
            # Verify worker exists and is active
            worker = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ? AND status = 'active'", (worker_id,)
            ).fetchone()
            if not worker:
                return []

            # Check worker capacity
            available_slots = worker["max_concurrent_sessions"] - worker["active_sessions"]
            if available_slots <= 0:
                return []

            max_to_steal = min(max_items, available_slots)

            # Find pending work items (highest priority first)
            rows = conn.execute(
                """SELECT * FROM work_queue
                WHERE status = 'pending'
                ORDER BY priority DESC, created_at ASC
                LIMIT ?""",
                (max_to_steal,),
            ).fetchall()

            for row in rows:
                work_id = row["id"]
                conn.execute(
                    """UPDATE work_queue SET
                        status = 'assigned', assigned_worker_id = ?, assigned_at = ?
                    WHERE id = ?""",
                    (worker_id, now, work_id),
                )
                conn.execute(
                    "UPDATE workers SET active_sessions = active_sessions + 1, total_sessions_handled = total_sessions_handled + 1 WHERE worker_id = ?",
                    (worker_id,),
                )
                stolen.append(cls._row_to_work_item(row))

        return stolen

    @classmethod
    def complete_work(cls, work_id: str, worker_id: str, success: bool = True) -> Optional[Dict[str, Any]]:
        """Mark a work item as completed or failed."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        new_status = "completed" if success else "failed"

        with transaction() as conn:
            work = conn.execute(
                "SELECT * FROM work_queue WHERE id = ? AND assigned_worker_id = ? AND status = 'assigned'",
                (work_id, worker_id),
            ).fetchone()
            if not work:
                return None

            conn.execute(
                """UPDATE work_queue SET
                    status = ?, completed_at = ?
                WHERE id = ?""",
                (new_status, now, work_id),
            )

            # Decrement worker's active sessions
            conn.execute(
                "UPDATE workers SET active_sessions = active_sessions - 1 WHERE worker_id = ? AND active_sessions > 0",
                (worker_id,),
            )

        return cls.get_work_item(work_id)

    @classmethod
    def migrate_session_work(cls, session_id: str, from_worker_id: str, to_worker_id: str) -> Dict[str, Any]:
        """Migrate all assigned work for a session from one worker to another (session migration)."""
        now = datetime.datetime.now(datetime.timezone.utc).isoformat()
        migrated_count = 0

        with transaction() as conn:
            # Verify both workers exist
            from_worker = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ?", (from_worker_id,)
            ).fetchone()
            to_worker = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ? AND status = 'active'", (to_worker_id,)
            ).fetchone()

            if not from_worker or not to_worker:
                return {"migrated": 0, "error": "Worker not found or not active"}

            # Check target worker capacity
            available_slots = to_worker["max_concurrent_sessions"] - to_worker["active_sessions"]
            if available_slots <= 0:
                return {"migrated": 0, "error": "Target worker at capacity"}

            # Find assigned work for this session on the source worker
            rows = conn.execute(
                """SELECT * FROM work_queue
                WHERE session_id = ? AND assigned_worker_id = ? AND status = 'assigned'
                LIMIT ?""",
                (session_id, from_worker_id, available_slots),
            ).fetchall()

            for row in rows:
                work_id = row["id"]
                conn.execute(
                    """UPDATE work_queue SET
                        assigned_worker_id = ?, assigned_at = ?
                    WHERE id = ?""",
                    (to_worker_id, now, work_id),
                )
                migrated_count += 1

            if migrated_count > 0:
                conn.execute(
                    "UPDATE workers SET active_sessions = active_sessions - ? WHERE worker_id = ? AND active_sessions >= ?",
                    (migrated_count, from_worker_id, migrated_count),
                )
                conn.execute(
                    "UPDATE workers SET active_sessions = active_sessions + ?, total_sessions_handled = total_sessions_handled + ? WHERE worker_id = ?",
                    (migrated_count, migrated_count, to_worker_id),
                )

        return {"migrated": migrated_count, "session_id": session_id, "from_worker": from_worker_id, "to_worker": to_worker_id}

    @classmethod
    def get_worker_workload(cls, worker_id: str) -> Dict[str, Any]:
        """Get current workload details for a worker."""
        conn, close_after = cls._get_conn()
        try:
            worker = conn.execute(
                "SELECT * FROM workers WHERE worker_id = ?", (worker_id,)
            ).fetchone()
            if not worker:
                return {"error": "Worker not found"}

            assigned_work = conn.execute(
                "SELECT * FROM work_queue WHERE assigned_worker_id = ? AND status = 'assigned'", (worker_id,)
            ).fetchall()

            return {
                "worker_id": worker_id,
                "status": worker["status"],
                "max_concurrent_sessions": worker["max_concurrent_sessions"],
                "active_sessions": worker["active_sessions"],
                "available_slots": worker["max_concurrent_sessions"] - worker["active_sessions"],
                "assigned_work": [cls._row_to_work_item(r) for r in assigned_work],
            }
        finally:
            if close_after:
                conn.close()

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

    @classmethod
    def _row_to_work_item(cls, row: Any) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "session_id": row["session_id"],
            "task_type": row["task_type"],
            "payload": json.loads(row["payload"] or "{}"),
            "priority": row["priority"],
            "status": row["status"],
            "assigned_worker_id": row["assigned_worker_id"],
            "created_at": row["created_at"],
            "assigned_at": row["assigned_at"],
            "completed_at": row["completed_at"],
        }


def init_fleet_tables() -> None:
    """Initialize fleet coordination tables."""
    conn = get_connection()
    close_after = get_db_path() != ":memory:"
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
        if close_after:
            conn.close()
