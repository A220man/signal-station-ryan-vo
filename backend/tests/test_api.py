"""Tests for FastAPI API endpoints."""
import pytest
from app.services.session_service import SessionService

@pytest.mark.asyncio
async def test_health_check(async_client):
    res = await async_client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert data["service"] == "signal-station"

@pytest.mark.asyncio
async def test_unauthenticated_request_rejected(async_client):
    res = await async_client.get("/api/sessions")
    assert res.status_code == 401
    assert "detail" in res.json()

@pytest.mark.asyncio
async def test_create_and_get_session(async_client, operator_token, viewer_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    payload = {
        "name": "Integration Test Session",
        "workspace_path": "test_workspace_alpha",
        "model": "gpt-4o-mini",
        "initial_goal": {
            "title": "Resolve Whitespace Discrepancies",
            "description": "Ensure code patcher handles tabs and spaces.",
            "verification_criteria": "Pytest passes",
            "token_budget": 45000,
            "time_budget_seconds": 1800
        }
    }
    create_res = await async_client.post("/api/sessions", json=payload, headers=headers)
    assert create_res.status_code == 201
    sess_data = create_res.json()
    session_id = sess_data["id"]
    assert sess_data["name"] == "Integration Test Session"
    assert sess_data["active_goal"]["title"] == "Resolve Whitespace Discrepancies"

    # Fetch as viewer
    view_headers = {"Authorization": f"Bearer {viewer_token}"}
    get_res = await async_client.get(f"/api/sessions/{session_id}", headers=view_headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == session_id

@pytest.mark.asyncio
async def test_archive_and_filter_session(async_client, operator_token, viewer_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    view_headers = {"Authorization": f"Bearer {viewer_token}"}

    create_res = await async_client.post("/api/sessions", json={"name": "Archivable Session"}, headers=headers)
    session_id = create_res.json()["id"]

    # Archive session
    arch_res = await async_client.post(f"/api/sessions/{session_id}/archive?archive=true", headers=headers)
    assert arch_res.status_code == 200
    assert arch_res.json()["is_archived"] is True

    # List without archived should exclude it
    list_active = await async_client.get("/api/sessions?include_archived=false", headers=view_headers)
    assert not any(s["id"] == session_id for s in list_active.json()["items"])

    # List with archived should include it
    list_all = await async_client.get("/api/sessions?include_archived=true", headers=view_headers)
    assert any(s["id"] == session_id for s in list_all.json()["items"])

@pytest.mark.asyncio
async def test_persistent_goal_update_and_accounting(async_client, operator_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    create_res = await async_client.post("/api/sessions", json={"name": "Goal Accounting Session"}, headers=headers)
    session_id = create_res.json()["id"]

    # Set new goal
    goal_res = await async_client.post(
        f"/api/sessions/{session_id}/goals",
        json={
            "title": "Refactor Data Pipeline",
            "description": "Optimize stream processing",
            "token_budget": 80000,
            "tokens_consumed": 2500,
            "status": "active"
        },
        headers=headers
    )
    assert goal_res.status_code == 200
    active_g = goal_res.json()["active_goal"]
    assert active_g["title"] == "Refactor Data Pipeline"
    assert active_g["tokens_consumed"] == 2500

    # Pause goal
    pause_res = await async_client.post(
        f"/api/sessions/{session_id}/goals",
        json={"status": "paused"},
        headers=headers
    )
    assert pause_res.json()["active_goal"]["status"] == "paused"

@pytest.mark.asyncio
async def test_step_dispatch_and_buffer_search(async_client, operator_token, viewer_token):
    headers = {"Authorization": f"Bearer {operator_token}"}
    view_headers = {"Authorization": f"Bearer {viewer_token}"}

    create_res = await async_client.post("/api/sessions", json={"name": "Step Dispatch Session"}, headers=headers)
    session_id = create_res.json()["id"]

    # Dispatch shell command step
    step_res = await async_client.post(
        f"/api/sessions/{session_id}/steps",
        json={"tool_name": "execute_command", "input_data": {"command": "echo 'SignalStationSearchKey123'"}, "tokens_consumed": 50},
        headers=headers
    )
    assert step_res.status_code == 200
    step_data = step_res.json()
    assert step_data["status"] == "success"

    # Search session buffer for key
    search_res = await async_client.get(
        f"/api/sessions/{session_id}/buffer/search?q=SignalStationSearchKey123",
        headers=view_headers
    )
    assert search_res.status_code == 200
    results = search_res.json()["results"]
    assert len(results) >= 1
    assert results[0]["step_number"] == 1

@pytest.mark.asyncio
async def test_role_denial_on_mutations(async_client, viewer_token):
    view_headers = {"Authorization": f"Bearer {viewer_token}"}
    # Viewer attempts to create session
    res = await async_client.post("/api/sessions", json={"name": "Forbidden Session"}, headers=view_headers)
    assert res.status_code == 403
    assert "Access denied" in res.json()["detail"]
