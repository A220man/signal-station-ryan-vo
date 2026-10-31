import { UserRole, Session, Goal, AgentStep, PatchResult, RiskCheckResult, PathContainmentResult, CompactionStats, CompactionResult, BenchmarkMetrics, Worker, WorkerListResponse, WorkerRegisterRequest, WorkerRegisterResponse, WorkerHeartbeatRequest, WorkerHeartbeatResponse, WorkItem, WorkItemCreate, WorkItemResponse, WorkItemListResponse, WorkAssignRequest, WorkStealRequest, WorkCompleteRequest, WorkCompleteResponse, SessionMigrateRequest, SessionMigrateResponse, WorkerWorkloadResponse } from "../types";

let inMemoryToken: string | null = null;
let currentUserRole: UserRole = "operator";

export const setAuthToken = (token: string | null, role: UserRole = "operator") => { inMemoryToken = token; currentUserRole = role; };
export const getAuthToken = () => inMemoryToken;
export const getCurrentRole = () => currentUserRole;

async function req<T>(url: string, opts: RequestInit = {}): Promise<T> {
  const headers = new Headers(opts.headers || {});
  headers.set("Content-Type", "application/json");
  if (inMemoryToken) headers.set("Authorization", `Bearer ${inMemoryToken}`);
  else headers.set("X-Demo-Role", currentUserRole);

  const res = await fetch(url, { ...opts, headers });
  if (!res.ok) {
    let err = `HTTP ${res.status}`;
    try { const b = await res.json(); if (b.detail) err = typeof b.detail === "string" ? b.detail : JSON.stringify(b.detail); } catch {}
    throw new Error(err);
  }
  return res.json() as Promise<T>;
}

export const api = {
  getAuthMode: () => req<{ demo_mode: boolean; app_env: string; oidc_issuer_url: string; available_roles: string[] }>("/api/auth/mode"),
  async loginDemo(username = "demo_operator", role: UserRole = "operator") {
    const d = await req<{ access_token: string }>("/api/auth/demo-token", { method: "POST", body: JSON.stringify({ username, role }) });
    setAuthToken(d.access_token, role);
    return d.access_token;
  },
  async listSessions(archived = false, search = ""): Promise<{ items: Session[]; total: number }> {
    const d = await req<{ items: any[]; total: number }>(`/api/sessions?include_archived=${archived}${search ? `&search=${encodeURIComponent(search)}` : ""}`);
    return { total: d.total, items: d.items.map(tSession) };
  },
  async getSession(id: string): Promise<Session> {
    return tSession(await req<any>(`/api/sessions/${id}`));
  },
  async createSession(name: string, workspacePath = "workspace_default", model = "gpt-4o-mini", goal?: { title: string; description: string }): Promise<Session> {
    const d = await req<any>("/api/sessions", {
      method: "POST",
      body: JSON.stringify({ name, workspace_path: workspacePath, model, initial_goal: goal ? { title: goal.title, description: goal.description, verification_criteria: "Passes tests" } : null })
    });
    return tSession(d);
  },
  async toggleArchive(id: string, archive: boolean): Promise<Session> {
    return tSession(await req<any>(`/api/sessions/${id}/archive?archive=${archive}`, { method: "POST" }));
  },
  async updateGoal(id: string, u: Partial<Goal>): Promise<Session> {
    return tSession(await req<any>(`/api/sessions/${id}/goals`, { method: "POST", body: JSON.stringify({ title: u.title, description: u.description, status: u.status, token_budget: u.tokenBudget }) }));
  },
  async dispatchStep(id: string, tool: string, inputData: Record<string, any>): Promise<AgentStep> {
    const d = await req<any>(`/api/sessions/${id}/steps`, { method: "POST", body: JSON.stringify({ tool_name: tool, input_data: inputData, tokens_consumed: 150 }) });
    return { id: d.id, sessionId: d.session_id, stepNumber: d.step_number, toolName: d.tool_name, inputData: d.input_data, outputData: d.output_data, status: d.status, executionTimeMs: d.execution_time_ms, createdAt: d.created_at };
  },
  async searchBuffer(id: string, q: string): Promise<any[]> {
    return (await req<{ results: any[] }>(`/api/sessions/${id}/buffer/search?q=${encodeURIComponent(q)}`)).results;
  },
  async applyPatch(file_path: string, original_snippet: string, modified_snippet: string, tolerance_mode = "normalized_whitespace", workspace_path?: string): Promise<PatchResult> {
    const d = await req<any>("/api/patches/apply", { method: "POST", body: JSON.stringify({ file_path, original_snippet, modified_snippet, tolerance_mode, workspace_path }) });
    return { success: d.success, strategyApplied: d.strategy_applied, hunksApplied: d.hunks_applied, totalHunks: d.total_hunks, diffPreview: d.diff_preview, message: d.message };
  },
  async checkCommandRisk(command: string): Promise<RiskCheckResult> {
    const d = await req<any>("/api/sandbox/check-command", { method: "POST", body: JSON.stringify({ command }) });
    return { command: d.command, riskLevel: d.risk_level, reason: d.reason, safeToExecute: d.safe_to_execute, flaggedPatterns: d.flagged_patterns };
  },
  async checkPathContainment(target_path: string, workspace_root?: string): Promise<PathContainmentResult> {
    const d = await req<any>("/api/sandbox/check-path", { method: "POST", body: JSON.stringify({ target_path, workspace_root }) });
    return { targetPath: d.target_path, workspaceRoot: d.workspace_root, isContained: d.is_contained, canonicalPath: d.canonical_path, errorMessage: d.error_message };
  },
  async getCompactionStats(): Promise<CompactionStats> {
    const d = await req<any>("/api/compaction/stats");
    return { totalEvents: d.total_events, totalEventBytes: d.total_event_bytes, eventsByType: d.events_by_type, databaseFileSizeBytes: d.database_file_size_bytes, supersededCandidateCount: d.superseded_candidate_count };
  },
  async runCompaction(prune = true, vacuum = false): Promise<CompactionResult> {
    const d = await req<any>("/api/compaction/run", { method: "POST", body: JSON.stringify({ prune_superseded_snapshots: prune, vacuum_database: vacuum }) });
    return { eventsScanned: d.events_scanned, eventsPruned: d.events_pruned, bytesReclaimed: d.bytes_reclaimed, compactionRatioPct: d.compaction_ratio_pct, durationMs: d.duration_ms, timestamp: d.timestamp };
  },
  async runBenchmark(): Promise<BenchmarkMetrics> {
    return tBench(await req<any>("/api/evaluation/run", { method: "POST", body: JSON.stringify({ run_all: true }) }));
  },
  async getBenchmarkHistory(): Promise<{ runs: BenchmarkMetrics[]; baselineComparison: any }> {
    const d = await req<any>("/api/evaluation/history");
    return { runs: d.runs.map(tBench), baselineComparison: d.baseline_comparison };
  },

  async registerWorker(payload: WorkerRegisterRequest): Promise<WorkerRegisterResponse> {
    return req<WorkerRegisterResponse>("/api/fleet/workers/register", { method: "POST", body: JSON.stringify(payload) });
  },

  async workerHeartbeat(payload: WorkerHeartbeatRequest): Promise<WorkerHeartbeatResponse> {
    return req<WorkerHeartbeatResponse>("/api/fleet/workers/heartbeat", { method: "POST", body: JSON.stringify(payload) });
  },

  async listWorkers(): Promise<WorkerListResponse> {
    return req<WorkerListResponse>("/api/fleet/workers");
  },

  async getWorker(id: string): Promise<Worker> {
    return req<Worker>(`/api/fleet/workers/${id}`);
  },

  async requestWorkerDrain(id: string): Promise<Worker> {
    return req<Worker>(`/api/fleet/workers/${id}/drain`, { method: "POST" });
  },

  async markStaleWorkers(): Promise<{ marked_inactive: number; timestamp: string }> {
    return req<{ marked_inactive: number; timestamp: string }>("/api/fleet/maintenance/mark-stale", { method: "POST" });
  },

  // --- Work Queue Methods ---
  async enqueueWork(payload: WorkItemCreate): Promise<WorkItemResponse> {
    return req<WorkItemResponse>("/api/fleet/work-queue/enqueue", { method: "POST", body: JSON.stringify(payload) });
  },

  async listPendingWork(sessionId?: string): Promise<WorkItemListResponse> {
    const url = sessionId ? `/api/fleet/work-queue/pending?session_id=${encodeURIComponent(sessionId)}` : "/api/fleet/work-queue/pending";
    return req<WorkItemListResponse>(url);
  },

  async assignWork(payload: WorkAssignRequest): Promise<WorkItemResponse> {
    return req<WorkItemResponse>("/api/fleet/work-queue/assign", { method: "POST", body: JSON.stringify(payload) });
  },

  async stealWork(payload: WorkStealRequest): Promise<WorkItemResponse[]> {
    return req<WorkItemResponse[]>("/api/fleet/work-queue/steal", { method: "POST", body: JSON.stringify(payload) });
  },

  async completeWork(payload: WorkCompleteRequest): Promise<WorkCompleteResponse> {
    return req<WorkCompleteResponse>("/api/fleet/work-queue/complete", { method: "POST", body: JSON.stringify(payload) });
  },

  async migrateSessionWork(payload: SessionMigrateRequest): Promise<SessionMigrateResponse> {
    return req<SessionMigrateResponse>("/api/fleet/work-queue/migrate", { method: "POST", body: JSON.stringify(payload) });
  },

  async getWorkerWorkload(workerId: string): Promise<WorkerWorkloadResponse> {
    return req<WorkerWorkloadResponse>(`/api/fleet/workers/${workerId}/workload`);
  },
};

function tSession(s: any): Session {
  return {
    id: s.id, name: s.name, workspacePath: s.workspace_path, model: s.model, status: s.status,
    isArchived: s.is_archived, createdAt: s.created_at, updatedAt: s.updated_at, stepCount: s.step_count || 0,
    activeGoal: s.active_goal ? {
      id: s.active_goal.id, sessionId: s.active_goal.session_id, title: s.active_goal.title, description: s.active_goal.description,
      status: s.active_goal.status, verificationCriteria: s.active_goal.verification_criteria, tokenBudget: s.active_goal.token_budget,
      tokensConsumed: s.active_goal.tokens_consumed, timeBudgetSeconds: s.active_goal.time_budget_seconds, elapsedSeconds: s.active_goal.elapsed_seconds,
      createdAt: s.active_goal.created_at, updatedAt: s.active_goal.updated_at
    } : null
  };
}

function tBench(d: any): BenchmarkMetrics {
  return {
    id: d.id, runTimestamp: d.run_timestamp, accuracy: d.accuracy, precisionScore: d.precision_score, recallScore: d.recall_score,
    f1Score: d.f1_score, patchSuccessRate: d.patch_success_rate, compactionRatio: d.compaction_ratio, meanLatencyMs: d.mean_latency_ms,
    totalScenarios: d.total_scenarios, passedScenarios: d.passed_scenarios, details: d.details || {}
  };
}
