export type UserRole = "viewer" | "operator" | "admin";

export interface User {
  userId: string;
  username: string;
  email: string;
  roles: UserRole[];
  isDemo: boolean;
}

export interface Goal {
  id: string;
  sessionId: string;
  title: string;
  description: string;
  status: "active" | "paused" | "completed" | "failed";
  verificationCriteria: string;
  tokenBudget: number;
  tokensConsumed: number;
  timeBudgetSeconds: number;
  elapsedSeconds: number;
  createdAt: string;
  updatedAt: string;
}

export interface Session {
  id: string;
  name: string;
  workspacePath: string;
  model: string;
  status: string;
  isArchived: boolean;
  createdAt: string;
  updatedAt: string;
  activeGoal?: Goal | null;
  stepCount: number;
}

export interface AgentStep {
  id: string;
  sessionId: string;
  stepNumber: number;
  toolName: string;
  inputData: Record<string, any>;
  outputData: Record<string, any>;
  status: string;
  executionTimeMs: number;
  createdAt: string;
}

export interface PatchResult {
  success: boolean;
  strategyApplied: string;
  hunksApplied: number;
  totalHunks: number;
  diffPreview: string;
  message: string;
}

export interface RiskCheckResult {
  command: string;
  riskLevel: "SAFE" | "GUARDED" | "PROHIBITED";
  reason: string;
  safeToExecute: boolean;
  flaggedPatterns: string[];
}

export interface PathContainmentResult {
  targetPath: string;
  workspaceRoot: string;
  isContained: boolean;
  canonicalPath: string;
  errorMessage?: string | null;
}

export interface CompactionStats {
  totalEvents: number;
  totalEventBytes: number;
  eventsByType: Record<string, number>;
  databaseFileSizeBytes: number;
  supersededCandidateCount: number;
}

export interface CompactionResult {
  eventsScanned: number;
  eventsPruned: number;
  bytesReclaimed: number;
  compactionRatioPct: number;
  durationMs: number;
  timestamp: string;
}

export interface BenchmarkMetrics {
  id: string;
  runTimestamp: string;
  accuracy: number;
  precisionScore: number;
  recallScore: number;
  f1Score: number;
  patchSuccessRate: number;
  compactionRatio: number;
  meanLatencyMs: number;
  totalScenarios: number;
  passedScenarios: number;
  details: Record<string, any>;
}
