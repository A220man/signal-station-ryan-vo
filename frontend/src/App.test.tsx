import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { App } from "./App";

vi.mock("./api/client", async () => {
  const actual = await vi.importActual<any>("./api/client");
  return {
    ...actual,
    api: {
      ...actual.api,
      listSessions: vi.fn().mockResolvedValue({
        total: 1,
        items: [
          {
            id: "ses_test123",
            name: "test-agent-session",
            workspacePath: "/tmp/workspace_test",
            model: "gpt-4o-mini",
            status: "active",
            isArchived: false,
            createdAt: "2026-10-18T00:00:00Z",
            updatedAt: "2026-10-18T00:00:00Z",
            stepCount: 2,
            activeGoal: {
              id: "gol_test123",
              sessionId: "ses_test123",
              title: "Test Goal",
              description: "Goal for testing UI",
              status: "active",
              verificationCriteria: "All tests pass",
              tokenBudget: 50000,
              tokensConsumed: 1200,
              timeBudgetSeconds: 3600,
              elapsedSeconds: 30,
              createdAt: "2026-10-18T00:00:00Z",
              updatedAt: "2026-10-18T00:00:00Z"
            }
          }
        ]
      }),
      getSession: vi.fn().mockResolvedValue({
        id: "ses_test123",
        name: "test-agent-session",
        workspacePath: "/tmp/workspace_test",
        model: "gpt-4o-mini",
        status: "active",
        isArchived: false,
        createdAt: "2026-10-18T00:00:00Z",
        updatedAt: "2026-10-18T00:00:00Z",
        stepCount: 2,
        activeGoal: {
          id: "gol_test123",
          sessionId: "ses_test123",
          title: "Test Goal",
          description: "Goal for testing UI",
          status: "active",
          verificationCriteria: "All tests pass",
          tokenBudget: 50000,
          tokensConsumed: 1200,
          timeBudgetSeconds: 3600,
          elapsedSeconds: 30,
          createdAt: "2026-10-18T00:00:00Z",
          updatedAt: "2026-10-18T00:00:00Z"
        }
      }),
      getCompactionStats: vi.fn().mockResolvedValue({
        totalEvents: 100,
        totalEventBytes: 50000,
        eventsByType: { "message.updated.1": 80, "session.created.1": 20 },
        databaseFileSizeBytes: 100000,
        supersededCandidateCount: 75
      }),
      getBenchmarkHistory: vi.fn().mockResolvedValue({
        runs: [],
        baselineComparison: {
          baseline_patch_success: 0.375,
          baseline_sandbox_precision: 0.833,
          baseline_sandbox_recall: 0.667,
          baseline_compaction_ratio: 0.0,
          engine_patch_success: 1.0,
          engine_sandbox_precision: 1.0,
          engine_sandbox_recall: 1.0,
          engine_compaction_ratio: 81.4
        }
      })
    }
  };
});

describe("Signal Station Frontend Component Suite", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Navbar with brand title and local demo badge", async () => {
    render(<App />);
    expect(screen.getByText("Signal Station")).toBeInTheDocument();
    expect(screen.getByText("Coding Agent Orchestrator")).toBeInTheDocument();
    expect(screen.getByText("Local Demo")).toBeInTheDocument();
  });

  it("loads and displays agent sessions and persistent goal on Dashboard", async () => {
    render(<App />);
    await waitFor(() => {
      expect(screen.getByText("test-agent-session")).toBeInTheDocument();
      expect(screen.getByText("Test Goal")).toBeInTheDocument();
    });
  });

  it("navigates across tabs to Patch Resilience and Safety Sandbox", async () => {
    render(<App />);
    
    // Switch to Patch Resilience tab
    const patchTab = screen.getByText("Patch Resilience");
    fireEvent.click(patchTab);
    expect(screen.getByText("Whitespace-Tolerant Patch Studio")).toBeInTheDocument();

    // Switch to Safety Sandbox tab
    const sandboxTab = screen.getByText("Safety Sandbox");
    fireEvent.click(sandboxTab);
    expect(screen.getByText("Shell Command Safety Sandbox")).toBeInTheDocument();
    expect(screen.getByText("Workspace Path Boundary Verifier")).toBeInTheDocument();
  });

  it("opens Auth modal when clicking role badge", async () => {
    render(<App />);
    const roleButton = screen.getByTitle("Click to switch role");
    fireEvent.click(roleButton);
    expect(screen.getByText("Authentication & Role Management")).toBeInTheDocument();
    expect(screen.getByText("Viewer (Read-Only)")).toBeInTheDocument();
    expect(screen.getByText("Operator (Standard Developer)")).toBeInTheDocument();
    expect(screen.getByText("Admin (System Administrator)")).toBeInTheDocument();
  });
});
