import React, { useState, useEffect } from "react";
import { Session, AgentStep } from "../types";
import { api, getCurrentRole } from "../api/client";

interface SessionDetailProps {
  sessionId: string;
  onBack: () => void;
}

export const SessionDetail: React.FC<SessionDetailProps> = ({ sessionId, onBack }) => {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [goalTitle, setGoalTitle] = useState("");
  const [goalDesc, setGoalDesc] = useState("");
  const [tokenBudget, setTokenBudget] = useState(50000);
  const [showGoalModal, setShowGoalModal] = useState(false);

  const [selectedTool, setSelectedTool] = useState("execute_command");
  const [toolCommand, setToolCommand] = useState("git status");
  const [toolFilePath, setToolFilePath] = useState("test.py");
  const [toolOriginal, setToolOriginal] = useState("");
  const [toolModified, setToolModified] = useState("");
  const [toolPrompt, setToolPrompt] = useState("");
  const [dispatching, setDispatching] = useState(false);
  const [lastStepResult, setLastStepResult] = useState<AgentStep | null>(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<any[]>([]);
  const [searching, setSearching] = useState(false);

  const role = getCurrentRole();
  const canOperate = role === "operator" || role === "admin";

  const loadSession = async () => {
    try {
      setLoading(true);
      const data = await api.getSession(sessionId);
      setSession(data);
      if (data.activeGoal) {
        setGoalTitle(data.activeGoal.title);
        setGoalDesc(data.activeGoal.description);
        setTokenBudget(data.activeGoal.tokenBudget);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load session");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadSession(); }, [sessionId]);

  const handleGoalStatus = async (status: "active" | "paused" | "completed") => {
    try {
      const updated = await api.updateGoal(sessionId, { status });
      setSession(updated);
    } catch (err: any) {
      alert(`Error updating goal: ${err.message}`);
    }
  };

  const handleSaveGoal = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const updated = await api.updateGoal(sessionId, { title: goalTitle, description: goalDesc, tokenBudget: Number(tokenBudget) });
      setSession(updated);
      setShowGoalModal(false);
    } catch (err: any) {
      alert(`Error saving goal: ${err.message}`);
    }
  };

  const handleDispatchStep = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!canOperate) return;
    setDispatching(true);
    let inputData: Record<string, any> = {};
    if (selectedTool === "execute_command") inputData = { command: toolCommand };
    else if (selectedTool === "read_file") inputData = { file_path: toolFilePath };
    else if (selectedTool === "edit_file") inputData = { file_path: toolFilePath, original_snippet: toolOriginal, modified_snippet: toolModified, tolerance_mode: "normalized_whitespace" };
    else if (selectedTool === "verify_goal") inputData = { verification_command: toolCommand };
    else if (selectedTool === "advisory_llm") inputData = { prompt: toolPrompt };

    try {
      const step = await api.dispatchStep(sessionId, selectedTool, inputData);
      setLastStepResult(step);
      await loadSession();
    } catch (err: any) {
      alert(`Step dispatch failed: ${err.message}`);
    } finally {
      setDispatching(false);
    }
  };

  const handleBufferSearch = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!searchQuery.trim()) { setSearchResults([]); return; }
    setSearching(true);
    try {
      const results = await api.searchBuffer(sessionId, searchQuery);
      setSearchResults(results);
    } catch (err: any) {
      alert(`Search error: ${err.message}`);
    } finally {
      setSearching(false);
    }
  };

  if (loading) return <div className="loading-state">Loading session details...</div>;
  if (error || !session) return <div className="error-banner">{error || "Session not found."}</div>;

  const goal = session.activeGoal;
  const tokenPercent = goal ? Math.min(100, Math.round((goal.tokensConsumed / goal.tokenBudget) * 100)) : 0;

  return (
    <div className="session-detail-container">
      <div className="session-detail-header" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "1.5rem" }}>
        <button className="btn btn-outline" onClick={onBack}>&larr; Back</button>
        <div>
          <h2>{session.name}</h2>
          <span className="font-mono text-muted">{session.workspacePath}</span>
        </div>
        <span className={`status-pill ${session.status}`}>{session.status}</span>
      </div>

      <div className="card">
        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "1rem" }}>
          <div>
            <h3>Persistent Session /goal</h3>
            {goal && <span className={`goal-status-badge ${goal.status}`}>{goal.status}</span>}
          </div>
          {canOperate && (
            <div style={{ display: "flex", gap: "0.5rem" }}>
              {goal?.status === "active" && <button className="btn btn-outline" onClick={() => handleGoalStatus("paused")}>Pause</button>}
              {goal?.status === "paused" && <button className="btn btn-primary" onClick={() => handleGoalStatus("active")}>Resume</button>}
              <button className="btn btn-secondary" onClick={() => setShowGoalModal(true)}>{goal ? "Edit Goal" : "+ Set /goal"}</button>
            </div>
          )}
        </div>

        {goal ? (
          <div>
            <h4>{goal.title}</h4>
            <p className="text-secondary">{goal.description}</p>
            <div className="meta-row"><strong>Verification:</strong> {goal.verificationCriteria}</div>
            <div className="progress-group">
              <div className="progress-label">
                <span>Tokens</span>
                <span>{goal.tokensConsumed.toLocaleString()} / {goal.tokenBudget.toLocaleString()} ({tokenPercent}%)</span>
              </div>
              <div className="progress-bar-track">
                <div className="progress-bar-fill" style={{ width: `${tokenPercent}%` }}></div>
              </div>
            </div>
          </div>
        ) : <p className="text-muted">No persistent goal configured.</p>}
      </div>

      <div className="card">
        <h3>Session Buffer Search</h3>
        <form onSubmit={handleBufferSearch} style={{ display: "flex", gap: "0.5rem", margin: "1rem 0" }}>
          <input type="text" placeholder="Search output buffer..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} style={{ flex: 1 }} />
          <button type="submit" className="btn btn-secondary" disabled={searching}>{searching ? "..." : "Search"}</button>
        </form>
        {searchResults.map((res, i) => (
          <div key={i} className="card" style={{ padding: "0.75rem", marginBottom: "0.5rem" }}>
            <div className="meta-row"><span>Step #{res.step_number} ({res.tool_name})</span></div>
            <pre className="font-mono" style={{ fontSize: "0.75rem" }}>{JSON.stringify(res.output_data, null, 2)}</pre>
          </div>
        ))}
      </div>

      {canOperate && (
        <div className="card">
          <h3>Tool Dispatcher</h3>
          <form onSubmit={handleDispatchStep}>
            <div className="form-group">
              <label>Tool</label>
              <select value={selectedTool} onChange={(e) => setSelectedTool(e.target.value)}>
                <option value="execute_command">execute_command (Sandboxed Shell)</option>
                <option value="read_file">read_file (Path Contained)</option>
                <option value="edit_file">edit_file (Whitespace Resilient)</option>
                <option value="verify_goal">verify_goal (Verification Suite)</option>
                <option value="advisory_llm">advisory_llm (Advisory)</option>
              </select>
            </div>

            {selectedTool === "execute_command" && (
              <div className="form-group"><label>Command</label><input type="text" value={toolCommand} onChange={(e) => setToolCommand(e.target.value)} /></div>
            )}
            {selectedTool === "read_file" && (
              <div className="form-group"><label>Path</label><input type="text" value={toolFilePath} onChange={(e) => setToolFilePath(e.target.value)} /></div>
            )}
            {selectedTool === "edit_file" && (
              <>
                <div className="form-group"><label>Path</label><input type="text" value={toolFilePath} onChange={(e) => setToolFilePath(e.target.value)} /></div>
                <div className="form-group"><label>Target</label><textarea rows={2} value={toolOriginal} onChange={(e) => setToolOriginal(e.target.value)} /></div>
                <div className="form-group"><label>Replacement</label><textarea rows={2} value={toolModified} onChange={(e) => setToolModified(e.target.value)} /></div>
              </>
            )}
            {selectedTool === "verify_goal" && (
              <div className="form-group"><label>Command</label><input type="text" value={toolCommand} onChange={(e) => setToolCommand(e.target.value)} /></div>
            )}
            {selectedTool === "advisory_llm" && (
              <div className="form-group"><label>Prompt</label><textarea rows={2} value={toolPrompt} onChange={(e) => setToolPrompt(e.target.value)} /></div>
            )}

            <button type="submit" className="btn btn-primary" disabled={dispatching}>{dispatching ? "Dispatching..." : "Dispatch Step"}</button>
          </form>

          {lastStepResult && (
            <div className="step-result-card">
              <h4>Step #{lastStepResult.stepNumber} ({lastStepResult.status})</h4>
              <pre className="font-mono">{JSON.stringify(lastStepResult.outputData, null, 2)}</pre>
            </div>
          )}
        </div>
      )}

      {showGoalModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <div className="modal-header"><h3>Configure /goal</h3><button className="modal-close" onClick={() => setShowGoalModal(false)}>&times;</button></div>
            <form onSubmit={handleSaveGoal}>
              <div className="modal-body">
                <div className="form-group"><label>Title *</label><input type="text" required value={goalTitle} onChange={(e) => setGoalTitle(e.target.value)} /></div>
                <div className="form-group"><label>Description *</label><textarea rows={2} required value={goalDesc} onChange={(e) => setGoalDesc(e.target.value)} /></div>
                <div className="form-group"><label>Token Budget</label><input type="number" value={tokenBudget} onChange={(e) => setTokenBudget(Number(e.target.value))} /></div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowGoalModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Save</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
