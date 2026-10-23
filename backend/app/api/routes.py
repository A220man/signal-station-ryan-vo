"""FastAPI API route definitions and endpoint handlers."""
import datetime
import pathlib
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from app.core.config import settings
from app.core.security import (
    require_role, create_demo_token, AuthenticatedUser, ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN
)
from app.core.database import log_audit, get_connection
from app.models.schemas import *
from app.services.session_service import SessionService
from app.services.sandbox_service import SandboxService
from app.services.patch_service import PatchService
from app.services.fleet_service import FleetService
from app.services.evaluation_service import EvaluationService

router = APIRouter(prefix="/api")

@router.get("/auth/mode", response_model=AuthModeResponse)
async def get_auth_mode():
    return AuthModeResponse(demo_mode=settings.demo_mode, app_env=settings.app_env, oidc_issuer_url=settings.oidc_issuer_url, oidc_client_id=settings.oidc_client_id, available_roles=[ROLE_VIEWER, ROLE_OPERATOR, ROLE_ADMIN])

@router.post("/auth/demo-token", response_model=DemoTokenResponse)
async def issue_demo_token(req: DemoTokenRequest, request: Request):
    if not settings.demo_mode or settings.app_env == "production":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Demo tokens disabled in production.")
    token = create_demo_token(username=req.username, role=req.role)
    ip = request.client.host if request.client else "127.0.0.1"
    log_audit("system", "issue_demo_token", "auth", req.username, req.role, ip)
    return DemoTokenResponse(access_token=token, token_type="Bearer", role=req.role, expires_in_minutes=settings.access_token_expire_minutes)

@router.post("/auth/exchange", response_model=TokenResponse)
async def exchange_oidc_code(req: OIDCTokenExchangeRequest, request: Request):
    if not req.code or not req.code_verifier:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing code or verifier.")
    role = ROLE_ADMIN if "admin" in req.code.lower() else (ROLE_VIEWER if "viewer" in req.code.lower() else ROLE_OPERATOR)
    token = create_demo_token(username=f"oidc_{req.code[:6]}", role=role)
    ip = request.client.host if request.client else "127.0.0.1"
    log_audit(f"oidc_{req.code[:6]}", "exchange_oidc", "auth", "token", role, ip)
    return TokenResponse(access_token=token, token_type="Bearer", expires_in=7200, user_id=f"usr_oidc_{req.code[:6]}", roles=[role])

@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(include_archived: bool = False, status: Optional[str] = None, search: Optional[str] = None, page: int = 1, page_size: int = 20, user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    res = SessionService.list_sessions(include_archived=include_archived, status_filter=status, search_query=search, page=page, page_size=page_size)
    return SessionListResponse(**res)

@router.post("/sessions", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
async def create_session(payload: SessionCreate, request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_OPERATOR))):
    initial_goal = payload.initial_goal.model_dump() if payload.initial_goal else None
    sess = SessionService.create_session(name=payload.name, workspace_path=payload.workspace_path, model=payload.model, initial_goal=initial_goal)
    ip = request.client.host if request.client else "127.0.0.1"
    log_audit(user.user_id, "create_session", "session", sess["id"], payload.name, ip)
    return SessionResponse(**sess)

@router.get("/sessions/{session_id}", response_model=SessionResponse)
async def get_session(session_id: str, user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    sess = SessionService.get_session(session_id)
    if not sess: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    return SessionResponse(**sess)

@router.post("/sessions/{session_id}/archive", response_model=SessionResponse)
async def toggle_session_archive(session_id: str, archive: bool = True, request: Request = None, user: AuthenticatedUser = Depends(require_role(ROLE_OPERATOR))):
    sess = SessionService.toggle_archive(session_id, archive)
    if not sess: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Session '{session_id}' not found.")
    ip = request.client.host if request and request.client else "127.0.0.1"
    log_audit(user.user_id, "archive_session", "session", session_id, str(archive), ip)
    return SessionResponse(**sess)

@router.post("/sessions/{session_id}/goals", response_model=SessionResponse)
async def set_or_update_goal(session_id: str, payload: GoalUpdate, request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_OPERATOR))):
    try:
        sess = SessionService.set_or_update_goal(session_id=session_id, title=payload.title, description=payload.description, status=payload.status, verification_criteria=payload.verification_criteria, token_budget=payload.token_budget, time_budget_seconds=payload.time_budget_seconds, tokens_consumed_delta=payload.tokens_consumed or 0, elapsed_seconds_delta=payload.elapsed_seconds or 0)
        ip = request.client.host if request.client else "127.0.0.1"
        log_audit(user.user_id, "update_goal", "goal", session_id, str(payload.status), ip)
        return SessionResponse(**sess)
    except ValueError as e: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.post("/sessions/{session_id}/steps", response_model=StepResponse)
async def dispatch_step(session_id: str, payload: StepCreate, request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_OPERATOR))):
    try:
        step = SessionService.execute_step(session_id=session_id, tool_name=payload.tool_name, input_data=payload.input_data, tokens_consumed=payload.tokens_consumed)
        ip = request.client.host if request.client else "127.0.0.1"
        log_audit(user.user_id, "dispatch_step", "step", step["id"], payload.tool_name, ip)
        return StepResponse(**step)
    except ValueError as e: raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.get("/sessions/{session_id}/buffer/search", response_model=BufferSearchResult)
async def search_session_buffer(session_id: str, q: str = Query(..., min_length=1), user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    return BufferSearchResult(**SessionService.search_buffer(session_id, q))

@router.post("/patches/apply", response_model=PatchApplyResponse)
async def apply_patch(payload: PatchApplyRequest, request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_OPERATOR))):
    ws = payload.workspace_path or "workspace_default"
    contained, canon_path, msg = SandboxService.verify_path_containment(ws, payload.file_path)
    if not contained: raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=msg)
    res = PatchService.apply_file_patch(pathlib.Path(canon_path), payload.original_snippet, payload.modified_snippet, payload.tolerance_mode)
    ip = request.client.host if request.client else "127.0.0.1"
    log_audit(user.user_id, "apply_patch", "file", payload.file_path, res["strategy_applied"], ip)
    return PatchApplyResponse(**res)

@router.post("/sandbox/check-command", response_model=CommandRiskCheckResponse)
async def check_command_risk(payload: CommandRiskCheckRequest, user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    return CommandRiskCheckResponse(**SandboxService.analyze_command_risk(payload.command))

@router.post("/sandbox/check-path", response_model=PathContainmentResponse)
async def check_path_containment(payload: PathContainmentRequest, user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    ws = payload.workspace_root or "workspace_default"
    contained, canon, msg = SandboxService.verify_path_containment(ws, payload.target_path)
    return PathContainmentResponse(target_path=payload.target_path, workspace_root=ws, is_contained=contained, canonical_path=canon, error_message=msg if not contained else None)

@router.get("/compaction/stats", response_model=CompactionStatsResponse)
async def get_compaction_stats(user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    return CompactionStatsResponse(**CompactionService.get_stats())

@router.post("/compaction/run", response_model=CompactionResponse)
async def run_compaction(payload: CompactionRunRequest, request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_ADMIN))):
    res = CompactionService.compact_events(session_id=payload.session_id, prune_superseded=payload.prune_superseded_snapshots, vacuum_database=payload.vacuum_database)
    ip = request.client.host if request.client else "127.0.0.1"
    log_audit(user.user_id, "run_compaction", "events", "all", str(res["events_pruned"]), ip)
    return CompactionResponse(**res)

@router.post("/evaluation/run", response_model=EvaluationMetricResponse)
async def run_evaluation(payload: EvaluationRunRequest, request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_OPERATOR))):
    res = EvaluationService.run_benchmark()
    ip = request.client.host if request.client else "127.0.0.1"
    log_audit(user.user_id, "run_eval", "benchmark", res["id"], str(res["accuracy"]), ip)
    return EvaluationMetricResponse(**res)

@router.get("/evaluation/history", response_model=EvaluationHistoryResponse)
async def get_evaluation_history(limit: int = 10, user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    return EvaluationHistoryResponse(**EvaluationService.get_history(limit=limit))

@router.post("/fleet/workers/register", response_model=WorkerRegisterResponse)
async def register_worker(payload: WorkerRegisterRequest, request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_OPERATOR))):
    res = FleetService.register_worker(
        worker_id=payload.worker_id,
        display_name=payload.display_name,
        capabilities=payload.capabilities,
        max_concurrent_sessions=payload.max_concurrent_sessions,
        metadata=payload.metadata,
    )
    if not res:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Worker registration failed")
    return WorkerRegisterResponse(
        worker_id=res["worker_id"],
        registered_at=res["registered_at"],
        status=res["status"],
        heartbeat_interval_seconds=FleetService.HEARTBEAT_INTERVAL_SECONDS,
    )

@router.post("/fleet/workers/heartbeat", response_model=WorkerHeartbeatResponse)
async def worker_heartbeat(payload: WorkerHeartbeatRequest, request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_OPERATOR))):
    try:
        res = FleetService.heartbeat(
            worker_id=payload.worker_id,
            active_sessions=payload.active_sessions,
            cpu_percent=payload.cpu_percent,
            memory_mb=payload.memory_mb,
            metadata=payload.metadata,
        )
        return WorkerHeartbeatResponse(**res)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

@router.get("/fleet/workers", response_model=WorkerListResponse)
async def list_workers(user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    return WorkerListResponse(**FleetService.list_workers())

@router.get("/fleet/workers/{worker_id}", response_model=WorkerResponse)
async def get_worker(worker_id: str, user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    worker = FleetService.get_worker(worker_id)
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Worker '{worker_id}' not found")
    return WorkerResponse(**worker)

@router.post("/fleet/workers/{worker_id}/drain", response_model=WorkerResponse)
async def request_worker_drain(worker_id: str, request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_ADMIN))):
    worker = FleetService.request_drain(worker_id)
    if not worker:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Worker '{worker_id}' not found")
    return WorkerResponse(**worker)

@router.post("/fleet/maintenance/mark-stale", response_model=Dict[str, Any])
async def mark_stale_workers(request: Request, user: AuthenticatedUser = Depends(require_role(ROLE_ADMIN))):
    count = FleetService.mark_inactive_stale()
    return {"marked_inactive": count, "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()}
@router.get("/audit/logs", response_model=List[AuditLogResponse])
async def list_audit_logs(limit: int = 50, user: AuthenticatedUser = Depends(require_role(ROLE_VIEWER))):
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, user_id, action, target_type, target_id, details, ip_address, created_at FROM audit_logs ORDER BY created_at DESC LIMIT ?;", (limit,)).fetchall()
        return [AuditLogResponse(id=r[0], user_id=r[1], action=r[2], target_type=r[3], target_id=r[4], details=r[5], ip_address=r[6], created_at=r[7]) for r in rows]
    finally:
        conn.close()
