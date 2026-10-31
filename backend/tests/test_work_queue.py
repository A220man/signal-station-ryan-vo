"""Tests for work queue: enqueue, assign, steal, complete, migrate."""
import pytest
import json
from app.services.fleet_service import FleetService


@pytest.fixture(autouse=True)
def setup_db():
    """Initialize database and fleet tables for each test."""
    from app.core.database import init_db, get_connection
    conn = get_connection()
    try:
        init_db(conn)
        conn.execute("DELETE FROM work_queue")
        conn.execute("DELETE FROM workers")
    finally:
        conn.close()


def test_enqueue_work():
    """Test enqueuing a work item."""
    # Register a worker first
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {"region": "us-east-1"})
    
    # Enqueue work
    work = FleetService.enqueue_work("ses_123", "code_review", {"file": "main.py"}, priority=5)
    
    assert work["id"].startswith("wrk_")
    assert work["session_id"] == "ses_123"
    assert work["task_type"] == "code_review"
    assert work["payload"] == {"file": "main.py"}
    assert work["priority"] == 5
    assert work["status"] == "pending"
    assert work["assigned_worker_id"] is None


def test_list_pending_work():
    """Test listing pending work items."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    
    FleetService.enqueue_work("ses_1", "task_a", {}, priority=1)
    FleetService.enqueue_work("ses_1", "task_b", {}, priority=10)
    FleetService.enqueue_work("ses_2", "task_c", {}, priority=5)
    
    # All pending work
    all_pending = FleetService.list_pending_work()
    assert len(all_pending) == 3
    # Highest priority first
    assert all_pending[0]["task_type"] == "task_b"
    assert all_pending[1]["task_type"] == "task_c"
    assert all_pending[2]["task_type"] == "task_a"
    
    # Filter by session
    ses1_work = FleetService.list_pending_work("ses_1")
    assert len(ses1_work) == 2


def test_assign_work_to_worker():
    """Test assigning work to a specific worker."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    work = FleetService.enqueue_work("ses_1", "code_review", {"file": "main.py"})
    
    assigned = FleetService.assign_work_to_worker("worker1", work["id"])
    
    assert assigned is not None
    assert assigned["status"] == "assigned"
    assert assigned["assigned_worker_id"] == "worker1"
    assert assigned["assigned_at"] is not None
    
    # Worker active_sessions should increment
    worker = FleetService.get_worker("worker1")
    assert worker["active_sessions"] == 1
    assert worker["total_sessions_handled"] == 1


def test_assign_work_capacity_limit():
    """Test that assignment fails when worker at capacity."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 1, {})  # max 1
    work1 = FleetService.enqueue_work("ses_1", "task1", {})
    work2 = FleetService.enqueue_work("ses_2", "task2", {})
    
    # First assignment succeeds
    assert FleetService.assign_work_to_worker("worker1", work1["id"]) is not None
    
    # Second assignment fails (at capacity)
    assert FleetService.assign_work_to_worker("worker1", work2["id"]) is None


def test_assign_work_inactive_worker():
    """Test that assignment fails for inactive worker."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    FleetService.request_drain("worker1")  # Set to draining
    work = FleetService.enqueue_work("ses_1", "task1", {})
    
    assert FleetService.assign_work_to_worker("worker1", work["id"]) is None


def test_steal_work():
    """Test work stealing by idle worker."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    FleetService.register_worker("worker2", "Worker 2", ["testing"], 2, {})
    
    FleetService.enqueue_work("ses_1", "task_a", {}, priority=1)
    FleetService.enqueue_work("ses_1", "task_b", {}, priority=10)
    FleetService.enqueue_work("ses_2", "task_c", {}, priority=5)
    
    # Worker2 steals work
    stolen = FleetService.steal_work("worker2", max_items=2)
    
    assert len(stolen) == 2
    # Highest priority first
    assert stolen[0]["task_type"] == "task_b"
    assert stolen[1]["task_type"] == "task_c"
    assert all(w["assigned_worker_id"] == "worker2" for w in stolen)
    assert all(w["status"] == "assigned" for w in stolen)
    
    # Worker2 active_sessions should increment
    worker2 = FleetService.get_worker("worker2")
    assert worker2["active_sessions"] == 2
    assert worker2["total_sessions_handled"] == 2
    
    # Only task_a should remain pending
    remaining = FleetService.list_pending_work()
    assert len(remaining) == 1
    assert remaining[0]["task_type"] == "task_a"


def test_steal_work_capacity_limit():
    """Test work stealing respects worker capacity."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 1, {})  # max 1
    FleetService.enqueue_work("ses_1", "task1", {})
    FleetService.enqueue_work("ses_2", "task2", {})
    
    # Steal max 5 but capacity is 1
    stolen = FleetService.steal_work("worker1", max_items=5)
    
    assert len(stolen) == 1


def test_steal_work_inactive_worker():
    """Test work stealing fails for inactive worker."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    FleetService.request_drain("worker1")
    FleetService.enqueue_work("ses_1", "task1", {})
    
    stolen = FleetService.steal_work("worker1")
    assert stolen == []


def test_complete_work():
    """Test completing a work item."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    work = FleetService.enqueue_work("ses_1", "code_review", {"file": "main.py"})
    FleetService.assign_work_to_worker("worker1", work["id"])
    
    completed = FleetService.complete_work(work["id"], "worker1", success=True)
    
    assert completed["status"] == "completed"
    assert completed["completed_at"] is not None
    
    # Worker active_sessions should decrement
    worker = FleetService.get_worker("worker1")
    assert worker["active_sessions"] == 0
    assert worker["total_sessions_handled"] == 1  # Total doesn't decrease


def test_complete_work_failed():
    """Test marking work as failed."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    work = FleetService.enqueue_work("ses_1", "code_review", {"file": "main.py"})
    FleetService.assign_work_to_worker("worker1", work["id"])
    
    failed = FleetService.complete_work(work["id"], "worker1", success=False)
    
    assert failed["status"] == "failed"
    assert failed["completed_at"] is not None


def test_complete_work_wrong_worker():
    """Test completing work assigned to different worker fails."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    FleetService.register_worker("worker2", "Worker 2", ["testing"], 2, {})
    work = FleetService.enqueue_work("ses_1", "code_review", {"file": "main.py"})
    FleetService.assign_work_to_worker("worker1", work["id"])
    
    # worker2 tries to complete worker1's work
    assert FleetService.complete_work(work["id"], "worker2") is None


def test_migrate_session_work():
    """Test migrating session work from one worker to another."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    FleetService.register_worker("worker2", "Worker 2", ["testing"], 2, {})
    
    work1 = FleetService.enqueue_work("ses_1", "task1", {})
    work2 = FleetService.enqueue_work("ses_1", "task2", {})
    work3 = FleetService.enqueue_work("ses_2", "task3", {})  # Different session
    
    FleetService.assign_work_to_worker("worker1", work1["id"])
    FleetService.assign_work_to_worker("worker1", work2["id"])
    FleetService.assign_work_to_worker("worker1", work3["id"])
    
    # Migrate ses_1 work from worker1 to worker2
    result = FleetService.migrate_session_work("ses_1", "worker1", "worker2")
    
    assert result["migrated"] == 2
    assert result["session_id"] == "ses_1"
    assert result["from_worker"] == "worker1"
    assert result["to_worker"] == "worker2"
    
    # Verify work reassigned
    w1 = FleetService.get_work_item(work1["id"])
    w2 = FleetService.get_work_item(work2["id"])
    w3 = FleetService.get_work_item(work3["id"])
    
    assert w1["assigned_worker_id"] == "worker2"
    assert w2["assigned_worker_id"] == "worker2"
    assert w3["assigned_worker_id"] == "worker1"  # Different session, not migrated
    
    # Verify worker counts updated
    worker1 = FleetService.get_worker("worker1")
    worker2 = FleetService.get_worker("worker2")
    assert worker1["active_sessions"] == 1  # Only ses_2 work remains
    assert worker2["active_sessions"] == 2  # ses_1 work migrated
    assert worker2["total_sessions_handled"] == 2


def test_migrate_session_work_capacity():
    """Test migration respects target worker capacity."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 3, {})
    FleetService.register_worker("worker2", "Worker 2", ["testing"], 1, {})  # max 1
    
    work1 = FleetService.enqueue_work("ses_1", "task1", {})
    work2 = FleetService.enqueue_work("ses_1", "task2", {})
    
    FleetService.assign_work_to_worker("worker1", work1["id"])
    FleetService.assign_work_to_worker("worker1", work2["id"])
    
    # Try to migrate 2 items to worker with capacity 1
    result = FleetService.migrate_session_work("ses_1", "worker1", "worker2")
    
    assert result["migrated"] == 1  # Only 1 fits
    assert "error" not in result


def test_migrate_session_work_invalid_workers():
    """Test migration fails for invalid workers."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    work = FleetService.enqueue_work("ses_1", "task1", {})
    FleetService.assign_work_to_worker("worker1", work["id"])
    
    # From non-existent worker
    result = FleetService.migrate_session_work("ses_1", "nonexistent", "worker1")
    assert result["migrated"] == 0
    assert "error" in result
    
    # To non-existent worker
    result = FleetService.migrate_session_work("ses_1", "worker1", "nonexistent")
    assert result["migrated"] == 0
    assert "error" in result
    
    # To inactive worker
    FleetService.request_drain("worker1")
    result = FleetService.migrate_session_work("ses_1", "worker1", "worker1")  # self-migrate to draining
    assert result["migrated"] == 0
    assert "error" in result


def test_get_worker_workload():
    """Test getting worker workload details."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 3, {})
    
    work1 = FleetService.enqueue_work("ses_1", "task1", {})
    work2 = FleetService.enqueue_work("ses_1", "task2", {})
    FleetService.assign_work_to_worker("worker1", work1["id"])
    FleetService.assign_work_to_worker("worker1", work2["id"])
    
    workload = FleetService.get_worker_workload("worker1")
    
    assert workload["worker_id"] == "worker1"
    assert workload["status"] == "active"
    assert workload["max_concurrent_sessions"] == 3
    assert workload["active_sessions"] == 2
    assert workload["available_slots"] == 1
    assert len(workload["assigned_work"]) == 2


def test_heartbeat_auto_assigns_work():
    """Test that heartbeat automatically assigns pending work to worker."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    FleetService.enqueue_work("ses_1", "task1", {}, priority=5)
    FleetService.enqueue_work("ses_2", "task2", {}, priority=10)
    
    # Worker heartbeats with 0 active sessions
    res = FleetService.heartbeat("worker1", active_sessions=0, cpu_percent=10.0, memory_mb=100, metadata={})
    
    assert len(res["assigned_work"]) == 2
    assert res["assigned_work"][0]["task_type"] == "task2"  # Higher priority first
    assert res["assigned_work"][1]["task_type"] == "task1"
    
    # Worker active_sessions should be updated
    worker = FleetService.get_worker("worker1")
    assert worker["active_sessions"] == 2
    assert worker["total_sessions_handled"] == 2


def test_heartbeat_drain_no_auto_assign():
    """Test that draining worker doesn't get auto-assigned work."""
    FleetService.register_worker("worker1", "Worker 1", ["coding"], 2, {})
    FleetService.request_drain("worker1")
    FleetService.enqueue_work("ses_1", "task1", {})
    
    # Worker heartbeats while draining
    res = FleetService.heartbeat("worker1", active_sessions=1, cpu_percent=10.0, memory_mb=100, metadata={})
    
    assert len(res["assigned_work"]) == 0
    assert res["drain_requested"] is True


