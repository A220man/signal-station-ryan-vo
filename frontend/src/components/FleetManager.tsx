import React, { useState, useEffect } from "react";
import { Worker, WorkerListResponse, WorkerRegisterRequest } from "../types";
import { api } from "../api/client";

export const FleetManager: React.FC = () => {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showRegisterModal, setShowRegisterModal] = useState(false);
  const [refreshing, setRefreshing] = useState(false);

  const [regWorkerId, setRegWorkerId] = useState("");
  const [regDisplayName, setRegDisplayName] = useState("");
  const [regCapabilities, setRegCapabilities] = useState("");
  const [regMaxConcurrent, setRegMaxConcurrent] = useState("1");

  const fetchWorkers = async () => {
    try {
      setError(null);
      const res: WorkerListResponse = await api.listWorkers();
      setWorkers(res.workers);
    } catch (err: any) {
      setError(err.message || "Failed to load workers");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchWorkers();
  }, []);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!regWorkerId.trim() || !regDisplayName.trim()) return;
    try {
      const caps = regCapabilities
        .split(",")
        .map((c) => c.trim())
        .filter((c) => c.length > 0);
      const payload: WorkerRegisterRequest = {
        workerId: regWorkerId.trim(),
        displayName: regDisplayName.trim(),
        capabilities: caps,
        maxConcurrentSessions: parseInt(regMaxConcurrent, 10) || 1,
        metadata: {},
      };
      await api.registerWorker(payload);
      setShowRegisterModal(false);
      setRegWorkerId("");
      setRegDisplayName("");
      setRegCapabilities("");
      setRegMaxConcurrent("1");
      fetchWorkers();
    } catch (err: any) {
      alert(err.message || "Registration failed");
    }
  };

  const handleDrain = async (workerId: string) => {
    if (!window.confirm(`Request drain for worker ${workerId}?`)) return;
    try {
      await api.requestWorkerDrain(workerId);
      fetchWorkers();
    } catch (err: any) {
      alert(err.message || "Drain request failed");
    }
  };

  const handleMarkStale = async () => {
    try {
      const res = await api.markStaleWorkers();
      alert(`Marked ${res.marked_inactive} workers as inactive`);
      fetchWorkers();
    } catch (err: any) {
      alert(err.message || "Failed to mark stale workers");
    }
  };

  const getStatusBadge = (status: Worker["status"]) => {
    const colors: Record<Worker["status"], string> = {
      active: "status-active",
      inactive: "status-inactive",
      draining: "status-draining",
    };
    return <span className={`status-badge ${colors[status]}`}>{status}</span>;
  };

  const formatTime = (iso: string | null) => {
    if (!iso) return "Never";
    return new Date(iso).toLocaleString();
  };

  return (
    <div className="fleet-manager">
      <div className="fleet-header">
        <h2>Agent Fleet</h2>
        <div className="fleet-actions">
          <button className="btn btn-secondary" onClick={() => { setRefreshing(true); fetchWorkers(); }} disabled={refreshing}>
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
          <button className="btn btn-primary" onClick={() => setShowRegisterModal(true)}>
            Register Worker
          </button>
          <button className="btn btn-warning" onClick={handleMarkStale}>
            Mark Stale
          </button>
        </div>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="loading">Loading workers...</div>
      ) : (
        <div className="workers-table-container">
          <table className="workers-table">
            <thead>
              <tr>
                <th>Worker ID</th>
                <th>Display Name</th>
                <th>Status</th>
                <th>Capabilities</th>
                <th>Max Sessions</th>
                <th>Active Sessions</th>
                <th>Total Handled</th>
                <th>Last Heartbeat</th>
                <th>Registered</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {workers.length === 0 ? (
                <tr>
                  <td colSpan={10} className="empty-state">
                    No workers registered. Click "Register Worker" to add one.
                  </td>
                </tr>
              ) : (
                workers.map((w) => (
                  <tr key={w.workerId}>
                    <td className="mono">{w.workerId}</td>
                    <td>{w.displayName}</td>
                    <td>{getStatusBadge(w.status)}</td>
                    <td className="capabilities">{w.capabilities.join(", ") || "—"}</td>
                    <td>{w.maxConcurrentSessions}</td>
                    <td>{w.activeSessions}</td>
                    <td>{w.totalSessionsHandled}</td>
                    <td className="mono">{formatTime(w.lastHeartbeatAt)}</td>
                    <td className="mono">{formatTime(w.registeredAt)}</td>
                    <td>
                      <div className="action-buttons">
                        {w.status === "active" && (
                          <button className="btn btn-sm btn-warning" onClick={() => handleDrain(w.workerId)}>
                            Drain
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      )}

      {showRegisterModal && (
        <div className="modal-overlay" onClick={() => setShowRegisterModal(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <h3>Register New Worker</h3>
            <form onSubmit={handleRegister}>
              <div className="form-group">
                <label htmlFor="workerId">Worker ID</label>
                <input
                  id="workerId"
                  type="text"
                  value={regWorkerId}
                  onChange={(e) => setRegWorkerId(e.target.value)}
                  placeholder="worker-001"
                  required
                  pattern="^[a-zA-Z0-9_-]+$"
                  title="Alphanumeric, underscore, hyphen only"
                />
              </div>
              <div className="form-group">
                <label htmlFor="displayName">Display Name</label>
                <input
                  id="displayName"
                  type="text"
                  value={regDisplayName}
                  onChange={(e) => setRegDisplayName(e.target.value)}
                  placeholder="Build Agent Alpha"
                  required
                />
              </div>
              <div className="form-group">
                <label htmlFor="capabilities">Capabilities (comma-separated)</label>
                <input
                  id="capabilities"
                  type="text"
                  value={regCapabilities}
                  onChange={(e) => setRegCapabilities(e.target.value)}
                  placeholder="patch, sandbox, evaluation"
                />
              </div>
              <div className="form-group">
                <label htmlFor="maxConcurrent">Max Concurrent Sessions</label>
                <input
                  id="maxConcurrent"
                  type="number"
                  value={regMaxConcurrent}
                  onChange={(e) => setRegMaxConcurrent(e.target.value)}
                  min="1"
                  max="10"
                  required
                />
              </div>
              <div className="modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowRegisterModal(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn btn-primary">
                  Register
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};