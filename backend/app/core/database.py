"""SQLite persistent database layer with transactional context and audit logging."""
import os
import sqlite3
import pathlib
import datetime
import contextlib
from typing import Generator, Any, Dict, List, Optional
from app.core.config import settings

def get_db_path() -> str:
    """Resolve database path, ensuring parent directory exists if using disk."""
    path = settings.database_path
    if path.startswith("sqlite:///:memory:") or path == ":memory:":
        return ":memory:"
    if path.startswith("sqlite:///"):
        path = path.replace("sqlite:///", "")
    p = pathlib.Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)

_mem_keepalive: Optional[sqlite3.Connection] = None

def get_connection() -> sqlite3.Connection:
    """Create a configured SQLite connection."""
    global _mem_keepalive
    db_p = get_db_path()
    if db_p == ":memory:":
        uri_str = "file:memdb?mode=memory&cache=shared"
        if _mem_keepalive is None:
            _mem_keepalive = sqlite3.connect(uri_str, uri=True)
            _mem_keepalive.execute("PRAGMA foreign_keys = ON;")
        conn = sqlite3.connect(uri_str, uri=True, timeout=15.0)
    else:
        conn = sqlite3.connect(db_p, timeout=15.0)
        conn.execute("PRAGMA journal_mode = WAL;")

    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

@contextlib.contextmanager
def transaction(conn: Optional[sqlite3.Connection] = None) -> Generator[sqlite3.Connection, None, None]:
    """Provide a transactional boundary with automatic commit or rollback."""
    should_close = False
    if conn is None:
        conn = get_connection()
        should_close = True
    try:
        conn.execute("BEGIN IMMEDIATE;")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        if should_close:
            conn.close()

def init_db(conn: Optional[sqlite3.Connection] = None) -> None:
    """Initialize schema tables if they do not exist."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True

    try:
        with conn:
            conn.execute("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                workspace_path TEXT NOT NULL,
                model TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                is_archived INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS goals (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                verification_criteria TEXT NOT NULL,
                token_budget INTEGER NOT NULL DEFAULT 50000,
                tokens_consumed INTEGER NOT NULL DEFAULT 0,
                time_budget_seconds INTEGER NOT NULL DEFAULT 3600,
                elapsed_seconds INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS steps (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                step_number INTEGER NOT NULL,
                tool_name TEXT NOT NULL,
                input_data TEXT NOT NULL,
                output_data TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'success',
                execution_time_ms REAL NOT NULL DEFAULT 0.0,
                created_at TEXT NOT NULL,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id TEXT PRIMARY KEY,
                aggregate_id TEXT NOT NULL,
                seq INTEGER NOT NULL,
                event_type TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (aggregate_id) REFERENCES sessions(id) ON DELETE CASCADE
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                action TEXT NOT NULL,
                target_type TEXT NOT NULL,
                target_id TEXT NOT NULL,
                details TEXT NOT NULL,
                ip_address TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """)

            conn.execute("""
            CREATE TABLE IF NOT EXISTS evaluation_runs (
                id TEXT PRIMARY KEY,
                run_timestamp TEXT NOT NULL,
                accuracy REAL NOT NULL,
                precision_score REAL NOT NULL,
                recall_score REAL NOT NULL,
                f1_score REAL NOT NULL,
                patch_success_rate REAL NOT NULL,
                compaction_ratio REAL NOT NULL,
                mean_latency_ms REAL NOT NULL,
                total_scenarios INTEGER NOT NULL,
                passed_scenarios INTEGER NOT NULL,
                details_json TEXT NOT NULL
            );
            """)

            # Fleet worker coordination tables
            conn.execute("""
            CREATE TABLE IF NOT EXISTS workers (
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
            );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_workers_status ON workers(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_workers_last_heartbeat ON workers(last_heartbeat_at);")

            conn.execute("""
            CREATE TABLE IF NOT EXISTS work_queue (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                task_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                priority INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'assigned', 'completed', 'failed')),
                assigned_worker_id TEXT,
                created_at TEXT NOT NULL,
                assigned_at TEXT,
                completed_at TEXT,
                FOREIGN KEY (session_id) REFERENCES sessions(id) ON DELETE CASCADE,
                FOREIGN KEY (assigned_worker_id) REFERENCES workers(worker_id) ON DELETE SET NULL
            );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_work_queue_status ON work_queue(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_work_queue_worker ON work_queue(assigned_worker_id);")

            # Indexes for high performance querying
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_archived ON sessions(is_archived);")
    finally:
        if close_after:
            conn.close()

def log_audit(
    user_id: str,
    action: str,
    target_type: str,
    target_id: str,
    details: str = "",
    ip_address: str = "127.0.0.1",
    conn: Optional[sqlite3.Connection] = None
) -> str:
    """Record an audit trail event for security compliance."""
    import uuid
    log_id = f"aud_{uuid.uuid4().hex[:12]}"
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    
    query = """
    INSERT INTO audit_logs (id, user_id, action, target_type, target_id, details, ip_address, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?);
    """
    params = (log_id, user_id, action, target_type, target_id, details, ip_address, now)

    if conn is not None:
        conn.execute(query, params)
    else:
        with transaction() as tx_conn:
            tx_conn.execute(query, params)
    return log_id
