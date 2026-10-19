"""Signal Station FastAPI application entrypoint."""
import contextlib
from typing import AsyncGenerator
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import settings
from app.core.database import init_db
from app.api.routes import router

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context: initialize database tables on startup."""
    init_db()
    yield

def create_app() -> FastAPI:
    """FastAPI application factory ensuring consistent configuration for local and Docker runtimes."""
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Autonomous coding agent orchestration platform featuring safety sandboxing, persistent session goals, whitespace-resilient patching, and event compaction.",
        lifespan=lifespan
    )

    # Cross-Origin Resource Sharing (CORS) configured for local development and SPA frontend
    application.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:3000",
            "http://localhost:3000",
            "http://127.0.0.1:8000",
            "http://localhost:8000"
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"]
    )

    # Security Headers Middleware
    @application.middleware("http")
    async def add_security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response

    # Mount API routes
    application.include_router(router)

    # Healthcheck endpoint
    @application.get("/health", tags=["System"])
    async def health_check():
        """Public readiness probe verifying server readiness and database connectivity."""
        return {
            "status": "healthy",
            "service": "signal-station",
            "version": settings.app_version,
            "environment": settings.app_env,
            "demo_mode": settings.demo_mode
        }

    return application

app = create_app()
