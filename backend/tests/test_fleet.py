"""Tests for fleet worker registration, heartbeat, and health monitoring."""
import pytest
from app.services.fleet_service import FleetService, init_fleet_tables
from app.core.database import init_db, get_connection, transaction
import datetime


@pytest.fixture(autouse=True)
def setup_db():
    """Initialize database and fleet tables for each test."""
    init_db()
    init_fleet_tables()
    # Clean up workers table
    with transaction() as conn:
        conn.execute("DELETE FROM workers")
    yield
    with transaction() as conn:
        conn.execute("DELETE FROM workers")


def test_register_worker():
    """Test registering a new worker."""
    worker = FleetService.register_worker(
        worker_id="worker-001",
        display_name="Build Agent Alpha",
        capabilities=["patch", "sandbox"],
        max_concurrent_sessions=2,
        metadata={"region": "us-east-1"},
    )

    assert worker is not None
    assert worker["worker_id"] == "worker-001"
    assert worker["display_name"] == "Build Agent Alpha"
    assert worker["capabilities"] == ["patch", "sandbox"]
    assert worker["max_concurrent_sessions"] == 2
    assert worker["status"] == "active"
    assert worker["active_sessions"] == 0
    assert worker["total_sessions_handled"] == 0
    assert worker["metadata"] == {"region": "us-east-1"}


def test_register_worker_upsert():
    """Test that re-registering updates existing worker."""
    FleetService.register_worker(
        worker_id="worker-001",
        display_name="Original Name",
        capabilities=["patch"],
        max_concurrent_sessions=1,
        metadata={},
    )

    worker = FleetService.register_worker(
        worker_id="worker-001",
        display_name="Updated Name",
        capabilities=["patch", "sandbox"],
        max_concurrent_sessions=3,
        metadata={"updated": True},
    )

    assert worker["display_name"] == "Updated Name"
    assert worker["capabilities"] == ["patch", "sandbox"]
    assert worker["max_concurrent_sessions"] == 3
    assert worker["metadata"] == {"updated": True}
    assert worker["status"] == "active"


def test_worker_heartbeat():
    """Test worker heartbeat updates state."""
    FleetService.register_worker(
        worker_id="worker-001",
        display_name="Agent",
        capabilities=[],
        max_concurrent_sessions=1,
        metadata={},
    )

    result = FleetService.heartbeat(
        worker_id="worker-001",
        active_sessions=2,
        cpu_percent=45.5,
        memory_mb=512,
        metadata={"current_task": "compaction"},
    )

    assert result["worker_id"] == "worker-001"
    assert result["acknowledged_at"] is not None
    assert result["drain_requested"] is False

    worker = FleetService.get_worker("worker-001")
    assert worker["active_sessions"] == 2
    assert worker["cpu_percent"] == 45.5
    assert worker["memory_mb"] == 512
    assert worker["metadata"] == {"current_task": "compaction"}
    assert worker["last_heartbeat_at"] is not None


def test_worker_heartbeat_not_registered():
    """Test heartbeat fails for unregistered worker."""
    with pytest.raises(ValueError, match="not registered"):
        FleetService.heartbeat(
            worker_id="unknown-worker",
            active_sessions=0,
            cpu_percent=None,
            memory_mb=None,
            metadata={},
        )


def test_list_workers():
    """Test listing workers with status counts."""
    FleetService.register_worker("w1", "Worker 1", ["a"], 1, {})
    FleetService.register_worker("w2", "Worker 2", ["b"], 2, {})
    FleetService.register_worker("w3", "Worker 3", ["c"], 1, {})

    # Heartbeat w1 to make it active
    FleetService.heartbeat("w1", 1, 10.0, 100, {})

    result = FleetService.list_workers()

    assert result["total"] == 3
    assert result["active_count"] >= 1
    assert len(result["workers"]) == 3


def test_get_worker():
    """Test getting a specific worker."""
    FleetService.register_worker("worker-001", "Test Worker", [], 1, {})

    worker = FleetService.get_worker("worker-001")
    assert worker is not None
    assert worker["worker_id"] == "worker-001"

    missing = FleetService.get_worker("nonexistent")
    assert missing is None


def test_request_drain():
    """Test requesting worker drain."""
    FleetService.register_worker("worker-001", "Test", [], 1, {})
    FleetService.heartbeat("worker-001", 2, 10.0, 100, {})

    worker = FleetService.request_drain("worker-001")
    assert worker["status"] == "draining"
    assert worker["active_sessions"] == 2

    # Heartbeat with 0 sessions should transition to inactive
    FleetService.heartbeat("worker-001", 0, 5.0, 50, {})
    worker = FleetService.get_worker("worker-001")
    assert worker["status"] == "inactive"


def test_mark_stale_workers():
    """Test marking stale workers as inactive."""
    FleetService.register_worker("worker-fresh", "Fresh", [], 1, {})
    FleetService.register_worker("worker-stale", "Stale", [], 1, {})

    # Heartbeat fresh worker
    FleetService.heartbeat("worker-fresh", 1, 10.0, 100, {})

    # Manually set stale worker's last_heartbeat to old time
    old_time = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=120)).isoformat()
    with transaction() as conn:
        conn.execute("UPDATE workers SET last_heartbeat_at = ? WHERE worker_id = ?", (old_time, "worker-stale"))

    count = FleetService.mark_inactive_stale()
    assert count == 1

    fresh = FleetService.get_worker("worker-fresh")
    stale = FleetService.get_worker("worker-stale")
    assert fresh["status"] == "active"
    assert stale["status"] == "inactive"


def test_worker_heartbeat_drain_transition():
    """Test worker transitions from draining to inactive when sessions complete."""
    FleetService.register_worker("worker-001", "Test", [], 1, {})
    FleetService.heartbeat("worker-001", 1, 10.0, 100, {})
    FleetService.request_drain("worker-001")

    # Still has active sessions
    result = FleetService.heartbeat("worker-001", 1, 10.0, 100, {})
    assert result["drain_requested"] is True

    worker = FleetService.get_worker("worker-001")
    assert worker["status"] == "draining"

    # Sessions complete
    result = FleetService.heartbeat("worker-001", 0, 5.0, 50, {})
    assert result["drain_requested"] is False

    worker = FleetService.get_worker("worker-001")
    assert worker["status"] == "inactive"


def test_heartbeat_interval_constant():
    """Test heartbeat interval constant is defined."""
    assert FleetService.HEARTBEAT_INTERVAL_SECONDS == 30
    assert FleetService.HEARTBEAT_TIMEOUT_SECONDS == 90