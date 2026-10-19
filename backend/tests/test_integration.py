"""Integration tests crossing the HTTP boundary for OIDC PKCE login and core workflows."""
import pytest
from app.core.security import generate_pkce_pair

@pytest.mark.asyncio
async def test_oidc_pkce_login_and_token_propagation(async_client):
    # Step 1: Client generates PKCE challenge pair
    pkce = generate_pkce_pair()
    auth_code = "auth_code_operator_xyz"

    # Step 2: Exchange authorization code and code_verifier across HTTP boundary
    exchange_payload = {
        "code": auth_code,
        "code_verifier": pkce["verifier"],
        "redirect_uri": "http://127.0.0.1:3000/callback"
    }
    exchange_res = await async_client.post("/api/auth/exchange", json=exchange_payload)
    assert exchange_res.status_code == 200
    token_data = exchange_res.json()
    assert "access_token" in token_data
    assert "operator" in token_data["roles"]

    token = token_data["access_token"]

    # Step 3: Propagate acquired token into authorized API request
    headers = {"Authorization": f"Bearer {token}"}
    session_res = await async_client.post(
        "/api/sessions",
        json={"name": "End-to-End OIDC Session", "model": "gpt-4o-mini"},
        headers=headers
    )
    assert session_res.status_code == 201
    created_session = session_res.json()
    assert created_session["name"] == "End-to-End OIDC Session"

    # Verify session can be fetched with token
    get_res = await async_client.get(f"/api/sessions/{created_session['id']}", headers=headers)
    assert get_res.status_code == 200
    assert get_res.json()["id"] == created_session["id"]

@pytest.mark.asyncio
async def test_oidc_exchange_rejection_on_missing_parameters(async_client):
    # Missing code verifier must be rejected
    bad_res = await async_client.post(
        "/api/auth/exchange",
        json={"code": "", "code_verifier": "", "redirect_uri": "http://127.0.0.1:3000"}
    )
    assert bad_res.status_code == 400

@pytest.mark.asyncio
async def test_full_agent_workflow_across_http_boundary(async_client, operator_token):
    headers = {"Authorization": f"Bearer {operator_token}"}

    # 1. Create session with initial goal
    sess_payload = {
        "name": "Full Lifecycle Workflow",
        "workspace_path": "ws_full_lifecycle",
        "initial_goal": {
            "title": "Optimize SQLite Queries",
            "description": "Add index on session_id",
            "token_budget": 30000,
            "verification_criteria": "echo 'all passed'"
        }
    }
    s_res = await async_client.post("/api/sessions", json=sess_payload, headers=headers)
    assert s_res.status_code == 201
    session_id = s_res.json()["id"]

    # 2. Dispatch a file edit step
    step_res = await async_client.post(
        f"/api/sessions/{session_id}/steps",
        json={
            "tool_name": "execute_command",
            "input_data": {"command": "echo 'SELECT * FROM sessions WHERE id = 1;'"},
            "tokens_consumed": 150
        },
        headers=headers
    )
    assert step_res.status_code == 200
    assert step_res.json()["status"] == "success"

    # 3. Verify goal completion
    verify_res = await async_client.post(
        f"/api/sessions/{session_id}/steps",
        json={
            "tool_name": "verify_goal",
            "input_data": {"verification_command": "echo 'tests passed'"},
            "tokens_consumed": 50
        },
        headers=headers
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["output_data"]["verified"] is True

    # Check that goal status transitioned to 'completed'
    updated_sess = await async_client.get(f"/api/sessions/{session_id}", headers=headers)
    assert updated_sess.json()["active_goal"]["status"] == "completed"

    # 4. Search buffer for execution trace
    search_res = await async_client.get(
        f"/api/sessions/{session_id}/buffer/search?q=SELECT",
        headers=headers
    )
    assert search_res.status_code == 200
    assert len(search_res.json()["results"]) >= 1

    # 5. Check audit logs trail
    audit_res = await async_client.get("/api/audit/logs", headers=headers)
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert any(l["target_id"] == session_id for l in logs)

@pytest.mark.asyncio
async def test_secret_redaction_in_errors(monkeypatch):
    from app.services.llm_service import LLMService
    # Generate runtime synthetic key string (never hardcoded literal)
    synthetic_key = "sk-" + ("0" * 24)
    raw_error_message = f"Failed to authenticate with key {synthetic_key} for user"

    from app.services.llm_service import redact_secrets
    sanitized = redact_secrets(raw_error_message)
    assert synthetic_key not in sanitized
    assert "[REDACTED_KEY]" in sanitized
