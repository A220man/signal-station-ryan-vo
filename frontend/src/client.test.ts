import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, setAuthToken, getAuthToken, getCurrentRole } from "./api/client";

describe("Typed API Client Suite", () => {
  beforeEach(() => {
    setAuthToken(null, "operator");
    vi.restoreAllMocks();
  });

  it("stores and manages in-memory authentication token", () => {
    expect(getAuthToken()).toBeNull();
    expect(getCurrentRole()).toBe("operator");

    setAuthToken("test-jwt-token-string", "admin");
    expect(getAuthToken()).toBe("test-jwt-token-string");
    expect(getCurrentRole()).toBe("admin");
  });

  it("dispatches requests with Bearer token when authenticated", async () => {
    setAuthToken("synthetic-token-value", "operator");

    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ demo_mode: true, app_env: "development", oidc_issuer_url: "http://localhost:8080", available_roles: ["viewer", "operator", "admin"] })
    });
    global.fetch = fetchMock;

    const res = await api.getAuthMode();
    expect(res.demo_mode).toBe(true);
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const callHeaders = fetchMock.mock.calls[0][1].headers as Headers;
    expect(callHeaders.get("Authorization")).toBe("Bearer synthetic-token-value");
  });

  it("transforms session snake_case API payload into typed camelCase model", async () => {
    const rawSession = {
      id: "ses_123",
      name: "Transform Test",
      workspace_path: "workspaces/test",
      model: "gpt-4o-mini",
      status: "active",
      is_archived: false,
      created_at: "2026-10-18T00:00:00Z",
      updated_at: "2026-10-18T00:00:00Z",
      step_count: 5,
      active_goal: {
        id: "gol_123",
        session_id: "ses_123",
        title: "Test Goal",
        description: "Goal description",
        status: "active",
        verification_criteria: "Lint passes",
        token_budget: 60000,
        tokens_consumed: 1500,
        time_budget_seconds: 7200,
        elapsed_seconds: 120,
        created_at: "2026-10-18T00:00:00Z",
        updated_at: "2026-10-18T00:00:00Z"
      }
    };

    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => rawSession
    });

    const session = await api.getSession("ses_123");
    expect(session.id).toBe("ses_123");
    expect(session.workspacePath).toBe("workspaces/test");
    expect(session.stepCount).toBe(5);
    expect(session.activeGoal?.tokenBudget).toBe(60000);
    expect(session.activeGoal?.tokensConsumed).toBe(1500);
  });
});
