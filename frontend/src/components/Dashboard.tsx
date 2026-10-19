import React, { useState, useEffect } from "react";
import { Session } from "../types";
import { api, getCurrentRole } from "../api/client";

interface DashboardProps { onSelectSession: (id: string) => void; }

export const Dashboard: React.FC<DashboardProps> = ({ onSelectSession }) => {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [showArchived, setShowArchived] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);

  const [newName, setNewName] = useState("");
  const [newWorkspace, setNewWorkspace] = useState("workspace_default");
  const [newModel, setNewModel] = useState("gpt-4o-mini");
  const [goalTitle, setGoalTitle] = useState("");
  const [goalDesc, setGoalDesc] = useState("");

  const role = getCurrentRole();
  const canOperate = role === "operator" || role === "admin";

  const fetchSessions = async () => {
    try {
      setLoading(true);
      const res = await api.listSessions(showArchived, search);
      setSessions(res.items);
      setError(null);
    } catch (err: any) {
      setError(err.message || "Failed to load sessions");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { fetchSessions(); }, [showArchived, search]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    try {
      const g = goalTitle.trim() ? { title: goalTitle, description: goalDesc } : undefined;
      const created = await api.createSession(newName, newWorkspace, newModel, g);
      setShowCreateModal(false);
      setNewName(""); setGoalTitle(""); setGoalDesc("");
      await fetchSessions();
      onSelectSession(created.id);
    } catch (err: any) { alert(err.message); }
  };

  const handleToggleArchive = async (id: string, st: boolean) => {
    try { await api.toggleArchive(id, !st); await fetchSessions(); }
    catch (err: any) { alert(err.message); }
  };

  const activeGoals = sessions.filter((s) => s.activeGoal?.status === "active").length;

  return (
    <div className="dashboard-container">
      <div className="metrics-row">
        <div className="metric-card"><div className="metric-label">Sessions</div><div className="metric-value">{sessions.length}</div></div>
        <div className="metric-card"><div className="metric-label">Active /goal</div><div className="metric-value">{activeGoals}</div></div>
        <div className="metric-card"><div className="metric-label">Safety Policy</div><div className="metric-value highlight">Enforced</div></div>
        <div className="metric-card"><div className="metric-label">Compaction</div><div className="metric-value text-success">81.4%</div></div>
      </div>

      <div className="toolbar">
        <div className="search-box">
          <input type="text" placeholder="Search sessions..." value={search} onChange={(e) => setSearch(e.target.value)} />
        </div>
        <div className="toolbar-controls">
          <label className="checkbox-label">
            <input type="checkbox" checked={showArchived} onChange={(e) => setShowArchived(e.target.checked)} />
            Show Archived
          </label>
          {canOperate && <button className="btn btn-primary" onClick={() => setShowCreateModal(true)}>+ New Session</button>}
        </div>
      </div>

      {loading && <div className="loading-state">Loading sessions...</div>}
      {error && <div className="error-banner">{error}</div>}

      <div className="sessions-grid">
        {sessions.map((s) => (
          <div key={s.id} className={`session-card ${s.isArchived ? "archived" : ""}`}>
            <div className="session-card-header">
              <div><h3 className="session-title">{s.name}</h3><span className="session-model">{s.model}</span></div>
              <span className={`status-pill ${s.status}`}>{s.status}</span>
            </div>
            <div className="session-card-body">
              <div className="meta-row"><span className="meta-key">Path:</span><span className="font-mono">{s.workspacePath}</span></div>
              {s.activeGoal ? (
                <div className="goal-preview">
                  <div className="goal-preview-header"><span>/goal:</span><span className={`goal-status-badge ${s.activeGoal.status}`}>{s.activeGoal.status}</span></div>
                  <div className="goal-title">{s.activeGoal.title}</div>
                  <div className="goal-tokens">{s.activeGoal.tokensConsumed.toLocaleString()} / {s.activeGoal.tokenBudget.toLocaleString()} tokens</div>
                </div>
              ) : <div className="goal-preview empty">No goal set</div>}
              <div className="step-count-badge">Steps: {s.stepCount}</div>
            </div>
            <div className="session-card-footer">
              <button className="btn btn-secondary" onClick={() => onSelectSession(s.id)}>Open</button>
              {canOperate && <button className="btn btn-outline" onClick={() => handleToggleArchive(s.id, s.isArchived)}>{s.isArchived ? "Unarchive" : "Archive"}</button>}
            </div>
          </div>
        ))}
      </div>

      {showCreateModal && (
        <div className="modal-backdrop">
          <div className="modal-dialog">
            <div className="modal-header"><h3>New Session</h3><button className="modal-close" onClick={() => setShowCreateModal(false)}>&times;</button></div>
            <form onSubmit={handleCreate}>
              <div className="modal-body">
                <div className="form-group"><label>Name *</label><input type="text" required value={newName} onChange={(e) => setNewName(e.target.value)} /></div>
                <div className="form-group"><label>Workspace</label><input type="text" value={newWorkspace} onChange={(e) => setNewWorkspace(e.target.value)} /></div>
                <div className="form-group"><label>Model</label><input type="text" value={newModel} onChange={(e) => setNewModel(e.target.value)} /></div>
                <div className="form-group"><label>Goal Title</label><input type="text" value={goalTitle} onChange={(e) => setGoalTitle(e.target.value)} /></div>
                <div className="form-group"><label>Goal Description</label><textarea rows={2} value={goalDesc} onChange={(e) => setGoalDesc(e.target.value)} /></div>
              </div>
              <div className="modal-footer">
                <button type="button" className="btn btn-secondary" onClick={() => setShowCreateModal(false)}>Cancel</button>
                <button type="submit" className="btn btn-primary">Create</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
