"""Pydantic models and serialization schemas for Signal Station."""
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

# --- Auth Schemas ---
class AuthModeResponse(BaseModel):
    demo_mode: bool
    app_env: str
    oidc_issuer_url: str
    oidc_client_id: str
    available_roles: List[str]

class DemoTokenRequest(BaseModel):
    username: str = Field(default="demo_operator", min_length=2, max_length=50)
    role: Literal["viewer", "operator", "admin"] = "operator"

class DemoTokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    role: str
    expires_in_minutes: int

class OIDCTokenExchangeRequest(BaseModel):
    code: str
    code_verifier: str
    redirect_uri: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user_id: str
    roles: List[str]

# --- Goal Schemas ---
class GoalCreate(BaseModel):
    title: str = Field(..., min_length=3, max_length=150)
    description: str = Field(..., min_length=5)
    verification_criteria: str = Field(default="all tests passing and lint clean")
    token_budget: int = Field(default=50000, ge=1000, le=1000000)
    time_budget_seconds: int = Field(default=3600, ge=60, le=86400)

class GoalUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[Literal["active", "paused", "completed", "failed"]] = None
    verification_criteria: Optional[str] = None
    token_budget: Optional[int] = None
    tokens_consumed: Optional[int] = None
    time_budget_seconds: Optional[int] = None
    elapsed_seconds: Optional[int] = None

class GoalResponse(BaseModel):
    id: str
    session_id: str
    title: str
    description: str
    status: str
    verification_criteria: str
    token_budget: int
    tokens_consumed: int
    time_budget_seconds: int
    elapsed_seconds: int
    created_at: str
    updated_at: str

# --- Step Schemas ---
class StepCreate(BaseModel):
    tool_name: Literal["read_file", "edit_file", "execute_command", "verify_goal", "advisory_llm"]
    input_data: Dict[str, Any]
    tokens_consumed: int = Field(default=150, ge=0)

class StepResponse(BaseModel):
    id: str
    session_id: str
    step_number: int
    tool_name: str
    input_data: Dict[str, Any]
    output_data: Dict[str, Any]
    status: str
    execution_time_ms: float
    created_at: str

# --- Session Schemas ---
class SessionCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    workspace_path: str = Field(default="workspace_default")
    model: str = Field(default="gpt-4o-mini")
    initial_goal: Optional[GoalCreate] = None

class SessionResponse(BaseModel):
    id: str
    name: str
    workspace_path: str
    model: str
    status: str
    is_archived: bool
    created_at: str
    updated_at: str
    active_goal: Optional[GoalResponse] = None
    step_count: int = 0

class SessionListResponse(BaseModel):
    items: List[SessionResponse]
    total: int
    page: int
    page_size: int

class BufferSearchResult(BaseModel):
    query: str
    matches_count: int
    results: List[Dict[str, Any]]

# --- Patch Schemas ---
class PatchApplyRequest(BaseModel):
    file_path: str
    original_snippet: str
    modified_snippet: str
    tolerance_mode: Literal["exact", "normalized_whitespace", "fuzzy_hunk"] = "normalized_whitespace"
    workspace_path: Optional[str] = None

class PatchApplyResponse(BaseModel):
    success: bool
    strategy_applied: str
    hunks_applied: int
    total_hunks: int
    diff_preview: str
    message: str

# --- Sandbox Schemas ---
class CommandRiskCheckRequest(BaseModel):
    command: str
    working_directory: Optional[str] = None

class CommandRiskCheckResponse(BaseModel):
    command: str
    risk_level: Literal["SAFE", "GUARDED", "PROHIBITED"]
    reason: str
    safe_to_execute: bool
    flagged_patterns: List[str]

class PathContainmentRequest(BaseModel):
    target_path: str
    workspace_root: Optional[str] = None

class PathContainmentResponse(BaseModel):
    target_path: str
    workspace_root: str
    is_contained: bool
    canonical_path: str
    error_message: Optional[str] = None

# --- Compaction Schemas ---
class CompactionRunRequest(BaseModel):
    session_id: Optional[str] = None
    prune_superseded_snapshots: bool = True
    vacuum_database: bool = False

class CompactionResponse(BaseModel):
    events_scanned: int
    events_pruned: int
    bytes_reclaimed: int
    compaction_ratio_pct: float
    duration_ms: float
    timestamp: str

class CompactionStatsResponse(BaseModel):
    total_events: int
    total_event_bytes: int
    events_by_type: Dict[str, int]
    database_file_size_bytes: int
    superseded_candidate_count: int

# --- AI/ML Evaluation Schemas ---
class EvaluationRunRequest(BaseModel):
    run_all: bool = True

class EvaluationMetricResponse(BaseModel):
    id: str
    run_timestamp: str
    accuracy: float
    precision_score: float
    recall_score: float
    f1_score: float
    patch_success_rate: float
    compaction_ratio: float
    mean_latency_ms: float
    total_scenarios: int
    passed_scenarios: int
    details: Dict[str, Any]

class EvaluationHistoryResponse(BaseModel):
    runs: List[EvaluationMetricResponse]
    baseline_comparison: Dict[str, Any]

# --- Audit Schemas ---
class AuditLogResponse(BaseModel):
    id: str
    user_id: str
    action: str
    target_type: str
    target_id: str
    details: str
    ip_address: str
    created_at: str
