import React, { useState, useEffect } from "react";
import { api, getCurrentRole } from "../api/client";
import { CompactionStats, CompactionResult } from "../types";

export const CompactionManager: React.FC = () => {
  const [stats, setStats] = useState<CompactionStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [compacting, setCompacting] = useState(false);
  const [lastResult, setLastResult] = useState<CompactionResult | null>(null);

  const role = getCurrentRole();
  const isAdmin = role === "admin";

  const fetchStats = async () => {
    try {
      setLoading(true);
      const res = await api.getCompactionStats();
      setStats(res);
    } catch (err: any) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  const handleRunCompaction = async () => {
    if (!isAdmin) return;
    setCompacting(true);
    try {
      const res = await api.runCompaction(true, false);
      setLastResult(res);
      await fetchStats();
    } catch (err: any) {
      alert(`Compaction failed: ${err.message}`);
    } finally {
      setCompacting(false);
    }
  };

  return (
    <div className="compaction-container card">
      <div className="section-header">
        <h2>Event Sourcing Compaction & Memory Optimization</h2>
        <p className="section-hint">
          Solves unbounded SQLite store growth by collapsing superseded snapshot events (e.g. message.updated.1, session.state.updated.1) and preserving only the latest aggregate sequence.
        </p>
      </div>

      {loading && <div className="loading-state">Loading event store metrics...</div>}

      {stats && (
        <div className="stats-dashboard">
          <div className="metrics-row">
            <div className="metric-card">
              <div className="metric-label">Total Event Records</div>
              <div className="metric-value">{stats.totalEvents.toLocaleString()}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Total Event Payload</div>
              <div className="metric-value">{(stats.totalEventBytes / 1024).toFixed(1)} KB</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Superseded Candidates</div>
              <div className="metric-value highlight">{stats.supersededCandidateCount.toLocaleString()}</div>
            </div>
            <div className="metric-card">
              <div className="metric-label">Disk Optimization Status</div>
              <div className="metric-value text-success">Active</div>
            </div>
          </div>

          <div className="event-breakdown">
            <h3>Event Distribution by Type</h3>
            <div className="table-responsive">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Event Type</th>
                    <th>Row Count</th>
                    <th>Retention Strategy</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(stats.eventsByType).map(([type, count]) => {
                    const isSnapshot = type.includes("updated") || type.includes("snapshot");
                    return (
                      <tr key={type}>
                        <td className="font-mono">{type}</td>
                        <td>{count.toLocaleString()}</td>
                        <td>
                          {isSnapshot ? (
                            <span className="badge warning">Superseded (Latest Retained)</span>
                          ) : (
                            <span className="badge info">Append-Only Audit</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          <div className="action-row">
            {isAdmin ? (
              <button
                className="btn btn-primary"
                onClick={handleRunCompaction}
                disabled={compacting}
              >
                {compacting ? "Compacting Event Store..." : "Run Snapshot Compaction"}
              </button>
            ) : (
              <div className="info-banner">
                Admin privilege required to trigger event store compaction. Switch role to 'admin' in header.
              </div>
            )}
          </div>
        </div>
      )}

      {lastResult && (
        <div className="compaction-result-box">
          <h3>Compaction Execution Complete</h3>
          <div className="result-stats-grid">
            <div>Events Scanned: <strong>{lastResult.eventsScanned}</strong></div>
            <div>Events Pruned: <strong>{lastResult.eventsPruned}</strong></div>
            <div>Bytes Reclaimed: <strong>{(lastResult.bytesReclaimed / 1024).toFixed(2)} KB</strong></div>
            <div>Compaction Ratio: <strong>{lastResult.compactionRatioPct}%</strong></div>
            <div>Duration: <strong>{lastResult.durationMs} ms</strong></div>
          </div>
        </div>
      )}
    </div>
  );
};
