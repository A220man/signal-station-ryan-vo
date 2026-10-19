"""Tests for OIDC security, PKCE verification, and RBAC authentication."""
import pytest
from fastapi import HTTPException
from app.core.config import settings
from app.core.security import (
    generate_pkce_pair,
    verify_pkce_challenge,
    create_demo_token,
    decode_token,
    AuthenticatedUser,
    ROLE_VIEWER,
    ROLE_OPERATOR,
    ROLE_ADMIN
)

def test_pkce_generation_and_verification():
    pkce = generate_pkce_pair()
    assert len(pkce["verifier"]) > 30
    assert len(pkce["challenge"]) > 30
    assert pkce["method"] == "S256"

    # Valid challenge matches
    assert verify_pkce_challenge(pkce["verifier"], pkce["challenge"]) is True

    # Modified verifier fails challenge
    assert verify_pkce_challenge(pkce["verifier"] + "bad", pkce["challenge"]) is False

def test_demo_token_issuance_and_decoding():
    token = create_demo_token(username="alice_operator", role=ROLE_OPERATOR)
    assert isinstance(token, str)

    payload = decode_token(token)
    assert payload["preferred_username"] == "alice_operator"
    assert ROLE_OPERATOR in payload["roles"]
    assert payload["iss"] == settings.oidc_issuer_url
    assert payload["aud"] == settings.oidc_audience

def test_refuse_demo_token_in_production(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "demo_mode", False)

    with pytest.raises(HTTPException) as exc_info:
        create_demo_token("test_user", ROLE_OPERATOR)
    assert exc_info.value.status_code == 403
    assert "production" in exc_info.value.detail.lower()

def test_rbac_role_hierarchy():
    viewer = AuthenticatedUser("u1", "viewer", "v@local", [ROLE_VIEWER])
    assert viewer.has_role(ROLE_VIEWER) is True
    assert viewer.has_role(ROLE_OPERATOR) is False
    assert viewer.has_role(ROLE_ADMIN) is False

    operator = AuthenticatedUser("u2", "operator", "o@local", [ROLE_OPERATOR])
    assert operator.has_role(ROLE_VIEWER) is True
    assert operator.has_role(ROLE_OPERATOR) is True
    assert operator.has_role(ROLE_ADMIN) is False

    admin = AuthenticatedUser("u3", "admin", "a@local", [ROLE_ADMIN])
    assert admin.has_role(ROLE_VIEWER) is True
    assert admin.has_role(ROLE_OPERATOR) is True
    assert admin.has_role(ROLE_ADMIN) is True

def test_invalid_token_rejection():
    # Synthetic malformed token value generated at runtime
    synthetic_bad_token = "synthetic_prefix." + ("0" * 32) + ".synthetic_sig"
    with pytest.raises(HTTPException) as exc:
        decode_token(synthetic_bad_token)
    assert exc.value.status_code == 401
