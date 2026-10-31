"""Test fixtures and test environment configuration."""
import pytest
import os
import httpx
from app.core.config import settings
from app.core import database as db_module
from app.core.database import init_db
from app.core.security import create_demo_token, ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN
from app.main import app

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Ensure in-memory SQLite database for isolated test execution."""
    # Reset the shared in-memory connection for test isolation
    if db_module._mem_keepalive is not None:
        db_module._mem_keepalive.close()
        db_module._mem_keepalive = None
    monkeypatch.setattr(settings, "database_path", "sqlite:///:memory:")
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "demo_mode", True)
    init_db()
    yield
    # Clean up after test
    if db_module._mem_keepalive is not None:
        db_module._mem_keepalive.close()
        db_module._mem_keepalive = None
def viewer_token():
    return create_demo_token(username="test_viewer", role=ROLE_VIEWER)

@pytest.fixture
def operator_token():
    return create_demo_token(username="test_operator", role=ROLE_OPERATOR)

@pytest.fixture
def admin_token():
    return create_demo_token(username="test_admin", role=ROLE_ADMIN)

@pytest.fixture
async def async_client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
