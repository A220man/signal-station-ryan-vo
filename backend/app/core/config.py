"""Application configuration and environment management."""
import os
import pathlib
from typing import Literal
from pydantic import BaseModel, Field

class Settings(BaseModel):
    app_name: str = "Signal Station"
    app_version: str = "1.0.0"
    app_env: Literal["development", "production", "test"] = "development"
    app_host: str = "127.0.0.1"
    app_port: int = 8000
    
    # Security and local demo mode
    demo_mode: bool = True
    secret_key: str = "signal-station-dev-secret-key-32-chars-min"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 120

    # Persistence
    database_path: str = "data/signal_station.db"

    # OIDC and SSO
    oidc_issuer_url: str = "http://127.0.0.1:8080/realms/signal-station"
    oidc_client_id: str = "signal-station-client"
    oidc_client_secret: str = ""
    oidc_audience: str = "signal-station-api"
    oidc_jwks_url: str = "http://127.0.0.1:8080/realms/signal-station/protocol/openid-connect/certs"

    # Multi-provider LLM settings (LLM_API_KEY is the sole secret)
    llm_api_key: str = ""
    llm_provider: str = "openai-compatible"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_timeout_seconds: float = 30.0

    # Workspace directory base
    workspace_root: str = "workspaces"

def get_settings() -> Settings:
    """Load settings from environment with validation for production security."""
    env = os.getenv("APP_ENV", "development").lower()
    demo_mode_env = os.getenv("DEMO_MODE", "true").lower() in ("true", "1", "yes")

    # Safeguard: Never permit demo mode in production
    if env == "production" and demo_mode_env:
        raise RuntimeError("CRITICAL SECURITY ERROR: DEMO_MODE cannot be enabled in production environment.")

    db_path = os.getenv("DATABASE_PATH", "data/signal_station.db")
    
    # Read product version if file exists
    version = "1.0.0"
    version_file = pathlib.Path(__file__).resolve().parents[3] / "VERSION"
    if version_file.is_file():
        version = version_file.read_text().strip()

    return Settings(
        app_name="Signal Station",
        app_version=version,
        app_env=env if env in ("development", "production", "test") else "development",
        app_host=os.getenv("APP_HOST", "127.0.0.1"),
        app_port=int(os.getenv("APP_PORT", "8000")),
        demo_mode=demo_mode_env if env != "production" else False,
        secret_key=os.getenv("SECRET_KEY", "signal-station-dev-secret-key-32-chars-min"),
        database_path=db_path,
        oidc_issuer_url=os.getenv("OIDC_ISSUER_URL", "http://127.0.0.1:8080/realms/signal-station"),
        oidc_client_id=os.getenv("OIDC_CLIENT_ID", "signal-station-client"),
        oidc_client_secret=os.getenv("OIDC_CLIENT_SECRET", ""),
        oidc_audience=os.getenv("OIDC_AUDIENCE", "signal-station-api"),
        oidc_jwks_url=os.getenv("OIDC_JWKS_URL", "http://127.0.0.1:8080/realms/signal-station/protocol/openid-connect/certs"),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_provider=os.getenv("LLM_PROVIDER", "openai-compatible"),
        llm_model=os.getenv("LLM_MODEL", "gpt-4o-mini"),
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.openai.com/v1"),
        llm_timeout_seconds=float(os.getenv("LLM_TIMEOUT_SECONDS", "30.0")),
        workspace_root=os.getenv("WORKSPACE_ROOT", "workspaces"),
    )

settings = get_settings()
